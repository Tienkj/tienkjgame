import json
import math
import os
import queue
import random
import select
import socket
import threading
import time
from array import array

import pygame

SERVER_V4 = "stamina-dusk.tun.ply.gg:16867"       # ipv4 tunnel
SERVER_V6 = "tienkjaz.duckdns.org:5555"   # ipv6 ở nhà
SERVER_ADDR = SERVER_V4

ROUTE_PREFERENCE = "auto"

CONFIG_FILE = "client_config.json"
DEFAULT_PORT = 5555

WIDTH, HEIGHT = 600, 720
FPS = 60
MAX_LEVELS = 50
SCORE_PER_LEVEL = 500
FIRE_DELAY = 8
PLAYER_SPEED = 7
MAX_HP = 5
MAX_BULLET_SPEED = 25
CHAT_KEEP = 120
MAX_PARTICLES = 420
MAX_THRUSTERS = 180
MAX_NET_BUFFER = 2 * 1024 * 1024
FIELD_MAX = {"user": 16, "pass": 32, "friend": 16, "chat": 200}


def bullet_count_for_level(level):
    level = int(level)
    if level >= 30:
        return 5
    if level >= 15:
        return 3
    if level >= 5:
        return 2
    return 1


DIFFS = {
    "EASY": {"name": "DỄ", "speed_mod": 0.72, "spawn_mod": 1.25, "coin_mod": 1.0, "color": (96, 214, 160)},
    "NORMAL": {"name": "THƯỜNG", "speed_mod": 1.00, "spawn_mod": 1.00, "coin_mod": 1.5, "color": (255, 200, 64)},
    "HARD": {"name": "KHÓ", "speed_mod": 1.35, "spawn_mod": 0.76, "coin_mod": 2.5, "color": (222, 64, 56)},
}

SKINS = {
    1: {"name": "Galaga Classic", "primary": (244, 233, 206), "wing": (222, 64, 56), "price": 0,
        "desc": "Phi thuyền cổ điển."},
    2: {"name": "Neon Fighter", "primary": (96, 214, 160), "wing": (100, 180, 230), "price": 150,
        "desc": "Phi thuyền neon."},
    3: {"name": "Chiến Hạm Vàng", "primary": (255, 200, 64), "wing": (255, 140, 50), "price": 300,
        "desc": "Giáp mạ vàng."},
    4: {"name": "Phượng Hoàng Lửa", "primary": (255, 95, 75), "wing": (255, 200, 64), "price": 500,
        "desc": "Hiệu ứng nâng cấp mạnh."},
}

PROJECTILES = {
    1: {"name": "CẦU LỬA", "main": (255, 106, 61), "accent": (255, 200, 64), "desc": "Quả cầu lửa nóng rực."},
    2: {"name": "CẦU TUYẾT", "main": (190, 235, 255), "accent": (100, 180, 230), "desc": "Cầu tuyết lạnh và sáng."},
    3: {"name": "CẦU PLASMA", "main": (96, 214, 160), "accent": (220, 255, 240), "desc": "Năng lượng plasma ổn định."},
    4: {"name": "TIA SÉT", "main": (236, 92, 140), "accent": (244, 233, 206), "desc": "Tia điện tốc độ cao."},
    5: {"name": "CẦU BĂNG", "main": (100, 180, 230), "accent": (220, 245, 255), "desc": "Cầu băng lạnh buốt."},
    6: {"name": "CẦU MẶT TRỜI", "main": (255, 200, 64), "accent": (255, 240, 180), "desc": "Năng lượng mặt trời cực sáng."},
}

POWERUPS = {
    "HP": {"name": "HỒI MÁU", "label": "HP", "color": (222, 64, 56), "accent": (255, 160, 150)},
    "SHIELD": {"name": "BẢO VỆ", "label": "KH", "color": (100, 180, 230), "accent": (220, 245, 255)},
    "UPGRADE": {"name": "THĂNG CẤP", "label": "UP", "color": (255, 200, 64), "accent": (255, 240, 180)},
}

SHIELD_FRAMES = 60 * 8
OVERDRIVE_FRAMES = 60 * 10
UPGRADE_FLASH_FRAMES = 75

# ============================================================
# pygame / âm thanh
# ============================================================
pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()
try:
    pygame.mixer.init()
except pygame.error:
    pass
AUDIO = pygame.mixer.get_init() is not None

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Đại Chiến Không Gian - Online | 50 Màn")
clock = pygame.time.Clock()

try:
    pygame.key.start_text_input()
except Exception:
    pass


class NullSound:
    def play(self, *args, **kwargs):
        return None

    def stop(self):
        return None

    def set_volume(self, _v):
        return None


def _make_tone(freq=440, duration=0.08, wave="sine", volume=0.16):
    if not AUDIO:
        return NullSound()
    rate = 44100
    n = max(1, int(rate * duration))
    out = array("h")
    for i in range(n):
        t = i / rate
        phase = 2.0 * math.pi * freq * t
        if wave == "square":
            val = 1.0 if math.sin(phase) >= 0 else -1.0
        elif wave == "noise":
            val = random.uniform(-1, 1)
        elif wave == "saw":
            val = 2.0 * ((freq * t) % 1.0) - 1.0
        else:
            val = math.sin(phase)
        fade = 1.0
        if i > n * 0.78:
            fade = max(0.0, (n - i) / (n * 0.22))
        sample = int(32767 * volume * val * fade)
        out.append(sample)
        out.append(sample)
    try:
        return pygame.mixer.Sound(buffer=out.tobytes())
    except pygame.error:
        return NullSound()


SFX = {
    "fire": _make_tone(680, 0.06, "saw"),
    "fire2": _make_tone(880, 0.06, "square"),
    "hit": _make_tone(220, 0.09, "noise"),
    "power": _make_tone(660, 0.16, "sine"),
    "upgrade": _make_tone(520, 0.35, "square"),
    "shield": _make_tone(390, 0.22, "sine"),
    "chat": _make_tone(960, 0.06, "sine"),
    "boss": _make_tone(110, 0.32, "saw"),
}


def snd(name):
    if G.sound_on:
        s = SFX.get(name)
        if s is not None:
            s.play()


# ============================================================
# Font / theme
# ============================================================

def load_font(size, bold=False):
    return pygame.font.SysFont("consolas,couriernew,dejavusansmono,liberationmono,menlo,monospace", size, bold=bold)


F_TITLE = load_font(26, True)
F_LARGE = load_font(28, True)
F_MED = load_font(17, True)
F_SMALL = load_font(14, True)
F_TINY = load_font(12)

PIX_BG = (16, 13, 26)
PIX_PANEL = (30, 24, 46)
PIX_PANEL_HI = (50, 40, 76)
PIX_INK = (10, 8, 16)
PIX_CREAM = (244, 233, 206)
PIX_DIM = (150, 138, 172)
PIX_ORANGE = (255, 106, 61)
PIX_GOLD = (255, 200, 64)
PIX_MINT = (96, 214, 160)
PIX_PINK = (236, 92, 140)
PIX_RED = (222, 64, 56)
PIX_BLUE = (100, 180, 230)
PIX_PURPLE = (150, 100, 210)
PIX_SHADOW = (150, 50, 40)


# ============================================================
# Global state
# ============================================================
class GameState:
    state = "SPLASH"
    splash = 0
    tick = 0
    sound_on = True
    bgm = None
    mouse = (0, 0)
    net = None
    user = None
    conn_lost = False
    route = ""
    auth_mode = "LOGIN"
    connecting = False
    auth_msg = ""
    auth_color = PIX_RED
    focus = None
    difficulty = "NORMAL"
    popup = False
    friends = {"me_score": 0, "friends": [], "requests": []}
    board = {"top": [], "rank": 0, "total": 0}
    board_tab = "FRIENDS"
    scroll = 0
    invite = None
    in_room = False
    partner = ""
    W = None
    mode = "solo"
    credited = 0
    submitted = False
    got_snapshot = False
    toast_msg = ""
    toast_color = PIX_MINT
    toast_until = 0.0
    save_dirty = False
    last_save = 0.0
    last_ping = 0.0
    last_refresh = 0.0
    chat_tab = "GLOBAL"
    chat_global = []
    chat_private = {}
    chat_target = None
    chat_unread = {}
    chat_badge_global = 0
    chat_scroll = 0


G = GameState()
P = {"coins": 500, "unlocked": {1}, "skin": 1, "bt": 1, "bs": 13, "hs": 0, "ps": 1}
fields = {"user": "", "pass": "", "friend": "", "chat": ""}
hits = []
prev_hits = []
particles = []
thrusters = []


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def toast(msg, ok=True, secs=3.0):
    G.toast_msg = str(msg)
    G.toast_color = PIX_MINT if ok else PIX_RED
    G.toast_until = time.time() + secs


def load_config():
    global SERVER_V4, SERVER_V6, SERVER_ADDR, ROUTE_PREFERENCE
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        fields["user"] = str(cfg.get("user", ""))[:FIELD_MAX["user"]]
        if isinstance(cfg.get("server_v4"), str) and cfg["server_v4"].strip():
            SERVER_V4 = SERVER_ADDR = cfg["server_v4"].strip()
        if isinstance(cfg.get("server_v6"), str):
            SERVER_V6 = cfg["server_v6"].strip()
        ps = int(cfg.get("projectile_style", 1))
        P["ps"] = ps if ps in PROJECTILES else 1
        P["difficulty"] = cfg.get("difficulty", "NORMAL")
        if P["difficulty"] in DIFFS:
            G.difficulty = P["difficulty"]
        pref = str(cfg.get("route_preference", "auto")).lower()
        if pref in ("auto", "ipv4", "ipv6"):
            ROUTE_PREFERENCE = pref
    except (OSError, ValueError, TypeError):
        pass


def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "user": fields["user"],
                "projectile_style": int(P.get("ps", 1)),
                "difficulty": G.difficulty,
                "server_v4": SERVER_V4,
                "server_v6": SERVER_V6,
                "route_preference": ROUTE_PREFERENCE,
            }, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def mark_dirty():
    G.save_dirty = True


# ============================================================
# GIAO THỨC UDP (giống server)
# ============================================================
import collections
import struct
import zlib

PROTO_VERSION = 1
(KIND_HELLO, KIND_WELCOME, KIND_REL, KIND_ACK, KIND_UNREL,
 KIND_PING, KIND_PONG, KIND_BYE, KIND_RESET) = range(1, 10)
HDR = struct.Struct("!BQ")
REL_HDR = struct.Struct("!IB")
ACK_BODY = struct.Struct("!II")
UNREL_HDR = struct.Struct("!HBB")
MIN_HELLO = 128
CHUNK = 1100
MAX_MSG = 128 * 1024
WINDOW = 96
MAX_TRIES = 12
MAX_PENDING = 3000


def encode_msg(msg):
    raw = json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(raw) > 200:
        z = zlib.compress(raw, 1)
        if len(z) < len(raw):
            return b"\x01" + z
    return b"\x00" + raw


def decode_msg(data):
    if not data:
        return None
    flag, body = data[0], data[1:]
    try:
        if flag == 1:
            d = zlib.decompressobj()
            body = d.decompress(body, MAX_MSG)
            if d.unconsumed_tail:
                return None
        elif flag != 0:
            return None
        msg = json.loads(body.decode("utf-8"))
    except (zlib.error, UnicodeDecodeError, ValueError):
        return None
    return msg if isinstance(msg, dict) else None


class Channel:
    def __init__(self, sid, raw_send):
        self.sid = sid
        self._raw = raw_send
        self.next_seq = 0
        self.unacked = {}
        self.pending = collections.deque()
        self.srtt = None
        self.rto = 0.3
        self.expect = 0
        self.rbuf = {}
        self.frag = bytearray()
        self.umsg = 0
        self.ulast = None
        self.upart = {}
        self.dead = False

    def _tx(self, dg):
        try:
            self._raw(dg)
        except OSError:
            pass

    def _hdr(self, kind):
        return HDR.pack(kind, self.sid)

    def send_msg(self, msg, reliable=True, now=None):
        if self.dead:
            return
        now = time.monotonic() if now is None else now
        try:
            data = encode_msg(msg)
        except (TypeError, ValueError):
            return
        if len(data) > MAX_MSG:
            return
        parts = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)] or [b""]
        if reliable:
            for i, part in enumerate(parts):
                seq = self.next_seq
                self.next_seq += 1
                flags = 1 if i == len(parts) - 1 else 0
                self.pending.append((seq, self._hdr(KIND_REL) + REL_HDR.pack(seq, flags) + part))
            if len(self.pending) > MAX_PENDING:
                self.dead = True
                return
            self._pump(now)
        else:
            if len(parts) > 255:
                return
            self.umsg = (self.umsg + 1) & 0xFFFF
            for i, part in enumerate(parts):
                self._tx(self._hdr(KIND_UNREL) + UNREL_HDR.pack(self.umsg, i, len(parts)) + part)

    def _pump(self, now):
        while self.pending and len(self.unacked) < WINDOW:
            seq, dg = self.pending.popleft()
            self.unacked[seq] = [dg, now, 0, now]
            self._tx(dg)

    def tick(self, now):
        if self.dead:
            return
        for seq, e in self.unacked.items():
            if now - e[1] >= self.rto * (1.6 ** min(e[2], 5)):
                if e[2] >= MAX_TRIES:
                    self.dead = True
                    return
                e[2] += 1
                e[1] = now
                self._tx(e[0])
        self._pump(now)

    def on_datagram(self, kind, body, now):
        out = []
        try:
            if kind == KIND_REL:
                self._on_rel(body, out)
            elif kind == KIND_ACK:
                self._on_ack(body, now)
            elif kind == KIND_UNREL:
                self._on_unrel(body, now, out)
        except struct.error:
            pass
        return out

    def _send_ack(self):
        cum = self.expect
        sack = 0
        for i in range(32):
            if cum + 1 + i in self.rbuf:
                sack |= 1 << i
        self._tx(self._hdr(KIND_ACK) + ACK_BODY.pack(cum & 0xFFFFFFFF, sack))

    def _on_rel(self, body, out):
        seq, flags = REL_HDR.unpack_from(body)
        chunk = body[REL_HDR.size:]
        if seq >= self.expect + WINDOW * 2:
            return
        if seq >= self.expect and seq not in self.rbuf:
            self.rbuf[seq] = (flags, chunk)
            while self.expect in self.rbuf:
                f, c = self.rbuf.pop(self.expect)
                self.expect += 1
                self.frag += c
                if len(self.frag) > MAX_MSG + 8192:
                    self.dead = True
                    return
                if f & 1:
                    msg = decode_msg(bytes(self.frag))
                    self.frag = bytearray()
                    if msg is not None:
                        out.append((msg, False))
        self._send_ack()

    def _on_ack(self, body, now):
        cum, sack = ACK_BODY.unpack_from(body)
        for seq in list(self.unacked):
            gap = seq - cum
            if seq < cum or (0 < gap <= 32 and (sack >> (gap - 1)) & 1):
                e = self.unacked.pop(seq)
                if e[2] == 0:
                    sample = max(0.0005, now - e[3])
                    self.srtt = sample if self.srtt is None else 0.875 * self.srtt + 0.125 * sample
                    self.rto = min(1.0, max(0.12, self.srtt * 2 + 0.04))
        self._pump(now)

    def _on_unrel(self, body, now, out):
        mid, idx, cnt = UNREL_HDR.unpack_from(body)
        chunk = body[UNREL_HDR.size:]
        if cnt == 0 or idx >= cnt:
            return
        if self.ulast is not None:
            diff = (mid - self.ulast) & 0xFFFF
            if diff == 0 or diff >= 0x8000:
                return
        if cnt == 1:
            data = chunk
        else:
            part = self.upart.get(mid)
            if part is None:
                if len(self.upart) >= 8:
                    del self.upart[min(self.upart, key=lambda k: self.upart[k][2])]
                part = self.upart[mid] = [cnt, {}, now]
            if part[0] != cnt:
                return
            part[1][idx] = chunk
            if len(part[1]) < cnt:
                return
            data = b"".join(part[1][i] for i in range(cnt))
            del self.upart[mid]
        msg = decode_msg(data)
        if msg is None:
            return
        self.ulast = mid
        for k in [k for k, v in self.upart.items() if now - v[2] > 1.5 or ((k - mid) & 0xFFFF) >= 0x8000]:
            del self.upart[k]
        out.append((msg, True))


HANDSHAKE_TIMEOUT = 6.0
KEEPALIVE_EVERY = 4.0
SERVER_SILENCE_LIMIT = 20.0


class Net:
    """Kết nối UDP tới server. Thử đồng thời IPv4 + IPv6, đo RTT, chọn đường tốt nhất."""

    def __init__(self):
        self.q = queue.Queue()
        self.outq = queue.Queue()
        self.closed = False
        self.route = ""
        self.rtt = None
        self.thread = None

    def start(self, first_msg):
        self.thread = threading.Thread(target=self._run, args=(first_msg,), daemon=True)
        self.thread.start()

    def send(self, msg, reliable=True):
        if not self.closed:
            self.outq.put((msg, bool(reliable)))

    def close(self):
        self.closed = True
        t = self.thread
        if t is not None and t is not threading.current_thread():
            t.join(0.4)

    @staticmethod
    def _tune(sock):
        sock.setblocking(False)
        if hasattr(socket, "SIO_UDP_CONNRESET"):
            try:
                sock.ioctl(socket.SIO_UDP_CONNRESET, False)
            except (OSError, ValueError):
                pass

    def _targets(self):
        out = []
        for label, family, spec in (("IPv4", socket.AF_INET, SERVER_V4), ("IPv6", socket.AF_INET6, SERVER_V6)):
            if not spec:
                continue
            try:
                host, port = parse_server(spec)
                infos = socket.getaddrinfo(host, port, family, socket.SOCK_DGRAM)
            except (ValueError, OSError):
                continue
            if not infos:
                continue
            try:
                s = socket.socket(family, socket.SOCK_DGRAM)
                self._tune(s)
            except OSError:
                continue
            out.append((label, s, [i[4] for i in infos[:2]]))
        return out

    # ============================================================
    # HANDSHAKE: gửi HELLO cả 2 đường, thu WELCOME, đo RTT, chọn nhanh nhất
    # ============================================================
    def _handshake(self, targets):
        nonce = int.from_bytes(os.urandom(8), "big") or 1
        hello = HDR.pack(KIND_HELLO, nonce) + bytes([PROTO_VERSION]) + b"\0" * (MIN_HELLO - HDR.size - 1)
        label_of = {t[1]: t[0] for t in targets}
        socks = [t[1] for t in targets]
        expected = len(targets)

        # --- Bước 1: gửi HELLO liên tục, gom WELCOME từ CẢ 2 đường ---
        welcomes = []
        seen = set()
        start = time.monotonic()
        deadline = start + 2.0
        next_send = start
        while not self.closed and time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_send:
                next_send = now + 0.35
                for _label, s, addrs in targets:
                    for a in addrs:
                        try:
                            s.sendto(hello, a)
                        except OSError:
                            pass
            try:
                ready, _, _ = select.select(socks, [], [], 0.04)
            except (OSError, ValueError):
                return None, "Lỗi socket."
            for s in ready:
                try:
                    data, frm = s.recvfrom(4096)
                except OSError:
                    continue
                if len(data) < HDR.size:
                    continue
                kind, sid_echo = HDR.unpack_from(data)
                if sid_echo != nonce:
                    continue
                if kind == KIND_WELCOME and len(data) >= HDR.size + 8:
                    label = label_of[s]
                    if label not in seen:
                        new_sid = struct.unpack_from("!Q", data, HDR.size)[0]
                        welcomes.append((label, s, frm, new_sid))
                        seen.add(label)
                elif kind == KIND_RESET:
                    return None, "Server không hỗ trợ phiên bản giao thức này."
            if len(welcomes) >= expected:
                break

        if not welcomes:
            return None, ("Không kết nối được tới server qua UDP (đã thử IPv4 + IPv6). "
                          "Kiểm tra mạng, địa chỉ server và cổng UDP (firewall/router).")

        # --- Bước 2: đo RTT cho từng đường đã WELCOME ---
        if len(welcomes) > 1:
            ping_ts = {}
            rtt_map = {}
            for label, sock, addr, sid in welcomes:
                t0 = time.monotonic()
                dg = HDR.pack(KIND_PING, sid) + struct.pack("!d", t0)
                try:
                    sock.sendto(dg, addr)
                    ping_ts[sock] = t0
                except OSError:
                    pass
            ping_deadline = time.monotonic() + 1.2
            pending = set(ping_ts.keys())
            while pending and time.monotonic() < ping_deadline:
                try:
                    ready, _, _ = select.select(list(pending), [], [], 0.04)
                except (OSError, ValueError):
                    break
                for s in ready:
                    try:
                        data, _frm = s.recvfrom(4096)
                    except OSError:
                        continue
                    if len(data) < HDR.size + 8:
                        continue
                    kind, _rsid = HDR.unpack_from(data)
                    if kind != KIND_PONG:
                        continue
                    try:
                        echoed = struct.unpack_from("!d", data, HDR.size)[0]
                    except struct.error:
                        continue
                    t0 = ping_ts.get(s)
                    if t0 is None or abs(echoed - t0) > 0.001:
                        continue
                    rtt_map[label_of[s]] = max(0.0005, time.monotonic() - t0)
                    pending.discard(s)
            for label, _sock, _addr, _sid in welcomes:
                if label not in rtt_map:
                    rtt_map[label] = 9.99

            if ROUTE_PREFERENCE == "ipv4" and "IPv4" in rtt_map:
                best_label = "IPv4"
            elif ROUTE_PREFERENCE == "ipv6" and "IPv6" in rtt_map:
                best_label = "IPv6"
            else:
                best_label = min(rtt_map, key=rtt_map.get)
            found = next((w for w in welcomes if w[0] == best_label), welcomes[0])
        else:
            found = welcomes[0]

        label, sock, addr, sid = found
        for _l, s, _a in targets:
            if s is not sock:
                try:
                    s.close()
                except OSError:
                    pass
        return (label, sock, addr, sid), None

    def _run(self, first):
        targets = self._targets()
        if not targets:
            self.closed = True
            self.q.put({"t": "_error", "msg": "Không phân giải được địa chỉ server (%s | %s)." % (SERVER_V4, SERVER_V6)})
            return
        found, err = self._handshake(targets)
        for _label, s, _a in targets:
            if found is None or s is not found[1]:
                try:
                    s.close()
                except OSError:
                    pass
        if found is None:
            cancelled = self.closed
            self.closed = True
            if err and not cancelled:
                self.q.put({"t": "_error", "msg": err})
            return
        label, sock, server_addr, sid = found
        self.route = label
        self.q.put({"t": "_route", "family": label})
        ch = Channel(sid, lambda dg: sock.sendto(dg, server_addr))
        ch.send_msg(first, True)
        last_rx = last_ping = time.monotonic()
        said_bye = False
        try:
            while not self.closed:
                for _ in range(300):
                    try:
                        item = self.outq.get_nowait()
                    except queue.Empty:
                        break
                    if item is not None:
                        ch.send_msg(item[0], item[1])
                try:
                    ready, _, _ = select.select([sock], [], [], 0.004)
                except (OSError, ValueError):
                    break
                gone = False
                if ready:
                    for _ in range(128):
                        try:
                            data, _frm = sock.recvfrom(4096)
                        except (BlockingIOError, InterruptedError):
                            break
                        except OSError:
                            continue
                        if len(data) < HDR.size:
                            continue
                        kind, rsid = HDR.unpack_from(data)
                        if rsid != sid:
                            continue
                        now = time.monotonic()
                        last_rx = now
                        body = data[HDR.size:]
                        if kind in (KIND_REL, KIND_ACK, KIND_UNREL):
                            for msg, _unrel in ch.on_datagram(kind, body, now):
                                self.q.put(msg)
                        elif kind == KIND_PONG and len(body) >= 8:
                            try:
                                self.rtt = max(0.0, now - struct.unpack_from("!d", body)[0])
                            except struct.error:
                                pass
                        elif kind in (KIND_BYE, KIND_RESET):
                            gone = said_bye = True
                            break
                if gone:
                    break
                now = time.monotonic()
                ch.tick(now)
                if ch.dead or now - last_rx > SERVER_SILENCE_LIMIT:
                    break
                if now - last_ping > KEEPALIVE_EVERY:
                    last_ping = now
                    ch._tx(HDR.pack(KIND_PING, sid) + struct.pack("!d", now))
        finally:
            self.closed = True
            if not said_bye:
                for _ in range(2):
                    ch._tx(HDR.pack(KIND_BYE, sid))
            try:
                sock.close()
            except OSError:
                pass
            self.q.put({"t": "_closed"})


def net_send(msg, reliable=True):
    if G.net and not G.net.closed:
        G.net.send(msg, reliable)


def parse_server(text):
    text = str(text).strip()
    if not text:
        raise ValueError("Địa chỉ server trống!")
    if text.startswith("["):
        end = text.find("]")
        if end < 0:
            raise ValueError("IPv6 thiếu ']'.")
        host = text[1:end]
        rest = text[end + 1:]
        port = DEFAULT_PORT
        if rest.startswith(":"):
            p = rest[1:]
            if not p.isdigit() or not (0 < int(p) < 65536):
                raise ValueError("Port không hợp lệ!")
            port = int(p)
        return host, port
    if ":" in text:
        host, p = text.rsplit(":", 1)
        if not p.isdigit() or not (0 < int(p) < 65536):
            raise ValueError("Port không hợp lệ!")
        return host, int(p)
    return text, DEFAULT_PORT


def send_save():
    G.save_dirty = False
    G.last_save = time.time()
    net_send({
        "t": "save",
        "data": {
            "coins": int(P["coins"]),
            "unlocked_skins": sorted(P["unlocked"]),
            "current_skin": int(P["skin"]),
            "bullet_type": 1,
            "bullet_speed": int(P["bs"]),
        },
    })


def submit_auth():
    if G.connecting:
        return
    user = fields["user"].strip()
    pw = fields["pass"]
    if len(user) < 3 or not pw:
        G.auth_msg, G.auth_color = "Nhập Tên (3-16) và Mật khẩu!", PIX_RED
        return
    if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for ch in user):
        G.auth_msg, G.auth_color = "Tên chỉ dùng chữ, số và dấu _. ", PIX_RED
        return
    if G.net:
        G.net.close()
    G.net = Net()
    G.conn_lost = False
    G.connecting = True
    G.auth_msg, G.auth_color = "Đang đo IPv4 + IPv6 và chọn đường tốt nhất...", PIX_GOLD
    G.net.start({"t": "auth", "mode": G.auth_mode.lower(), "user": user, "pass": pw})


def refresh_social():
    G.last_refresh = time.time()
    net_send({"t": "friends_get"})
    net_send({"t": "board_get"})
    net_send({"t": "chat_history"})


def go_login(msg=""):
    old = G.net
    G.net = None
    if old:
        old.close()
    G.user = None
    G.W = None
    G.in_room = False
    G.invite = None
    G.connecting = False
    G.popup = False
    G.chat_global.clear()
    G.chat_private.clear()
    G.chat_unread.clear()
    G.chat_target = None
    G.chat_badge_global = 0
    G.auth_msg, G.auth_color = msg, PIX_RED
    fields["pass"] = ""
    set_state("LOGIN")


def push_chat(bucket, entry):
    bucket.append(entry)
    if len(bucket) > CHAT_KEEP:
        del bucket[:-CHAT_KEEP]


def handle_net(m):
    t = m.get("t")
    if t == "auth_ok":
        d = m.get("data") or {}
        P["coins"] = int(d.get("coins", P["coins"]))
        P["unlocked"] = set(int(x) for x in d.get("unlocked_skins", [1]))
        P["skin"] = int(d.get("current_skin", 1)) if int(d.get("current_skin", 1)) in SKINS else 1
        P["bt"] = 1
        P["bs"] = clamp(int(d.get("bullet_speed", 13)), 13, MAX_BULLET_SPEED)
        P["hs"] = int(d.get("high_score", 0))
        G.user = str(m.get("user", fields["user"]))
        G.connecting = False
        G.auth_msg = ""
        G.last_ping = time.time()
        fields["pass"] = ""
        save_config()
        set_state("MENU")
        snd("upgrade")
        if G.route:
            rtt_txt = ""
            if G.net and G.net.rtt is not None:
                rtt_txt = " %.0fms" % (G.net.rtt * 1000)
            toast("UDP qua %s%s" % (G.route, rtt_txt))
    elif t == "auth_fail":
        G.connecting = False
        G.auth_msg, G.auth_color = str(m.get("msg", "Đăng nhập thất bại")), PIX_RED
        if G.net:
            G.net.close()
            G.net = None
    elif t == "_route":
        G.route = str(m.get("family", ""))
    elif t == "_error":
        G.connecting = False
        G.auth_msg, G.auth_color = str(m.get("msg", "Lỗi kết nối")), PIX_RED
    elif t == "_closed":
        if G.connecting:
            G.connecting = False
            G.auth_msg, G.auth_color = "Server đã đóng kết nối.", PIX_RED
        elif G.user:
            G.conn_lost = True
    elif t == "profile":
        P["hs"] = max(P["hs"], int(m.get("high_score", 0)))
    elif t == "friends":
        G.friends = {
            "me_score": int(m.get("me_score", 0)),
            "friends": m.get("friends", []) if isinstance(m.get("friends", []), list) else [],
            "requests": m.get("requests", []) if isinstance(m.get("requests", []), list) else [],
        }
    elif t == "board":
        G.board = m
    elif t == "notice":
        toast(m.get("msg", ""), bool(m.get("ok", True)))
        if m.get("ok", True):
            snd("power")
    elif t == "invited":
        G.invite = {"from": str(m.get("from", "?")), "t": time.time()}
        snd("power")
    elif t == "room_start":
        start_coop(str(m.get("role", "host")), str(m.get("partner", "?")))
    elif t == "room_msg":
        handle_room_msg(m.get("d") or {})
    elif t == "room_end":
        handle_room_end()
    elif t == "chat_history":
        G.chat_global.clear()
        for e in m.get("global", []) or []:
            if isinstance(e, dict):
                push_chat(G.chat_global, {"from": e.get("from", "?"), "msg": e.get("msg", ""), "ts": e.get("ts", 0)})
    elif t == "chat":
        scope = m.get("scope")
        if scope == "global":
            e = {"from": m.get("from", "?"), "msg": m.get("msg", ""), "ts": time.time()}
            push_chat(G.chat_global, e)
            if G.state == "CHAT" and G.chat_tab == "GLOBAL":
                snd("chat")
            elif m.get("from") != G.user:
                G.chat_badge_global += 1
                toast("[Tổng] %s: %s" % (str(e["from"])[:12], str(e["msg"])[:35]))
        elif scope == "private":
            other = m.get("to") if m.get("echo") else m.get("from")
            if other is None:
                return
            other = str(other)
            e = {"from": m.get("from", "?"), "msg": m.get("msg", ""), "ts": time.time()}
            push_chat(G.chat_private.setdefault(other, []), e)
            if not m.get("echo") and not (G.state == "CHAT" and G.chat_tab == "PRIVATE" and G.chat_target == other):
                G.chat_unread[other] = G.chat_unread.get(other, 0) + 1
                snd("chat")
                toast("[%s] %s" % (other[:12], str(e["msg"])[:35]))


def pump_net():
    net = G.net
    if not net:
        return
    for _ in range(160):
        try:
            m = net.q.get_nowait()
        except queue.Empty:
            break
        handle_net(m)
        if G.net is not net:
            break


# ============================================================
# Pixel drawing helpers
# ============================================================
_pixel_cache = {}


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def chamfer_points(rect, c=4):
    x, y, w, h = pygame.Rect(rect)
    return [(x + c, y), (x + w - c, y), (x + w, y + c), (x + w, y + h - c),
            (x + w - c, y + h), (x + c, y + h), (x, y + h - c), (x, y + c)]


def draw_wavy_rect(rect, border=PIX_CREAM, fill=PIX_PANEL, width=2, amp=2):
    rect = pygame.Rect(rect)
    cut = 4 if min(rect.w, rect.h) >= 24 else 2
    pts = chamfer_points(rect, cut)
    if width >= 2:
        pygame.draw.polygon(screen, PIX_INK, [(a + 3, b + 3) for a, b in pts])
    pygame.draw.polygon(screen, fill[:3], pts)
    pygame.draw.polygon(screen, border[:3], pts, max(1, width))


def text(txt, font, color, x, y, anchor="topleft"):
    s = font.render(str(txt), False, color)
    r = s.get_rect(**{anchor: (int(x), int(y))})
    if font in (F_TITLE, F_LARGE):
        sh = PIX_INK if tuple(color[:3]) == PIX_RED else PIX_SHADOW
        screen.blit(font.render(str(txt), False, sh), r.move(2, 2))
    screen.blit(s, r)
    return r


def wrap_text(txt, font, max_w):
    lines, cur = [], ""
    for word in str(txt).split():
        trial = (cur + " " + word).strip()
        if cur and font.size(trial)[0] > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


_GOOD_BASE = {(37, 104, 78)}
_BAD_BASE = {(104, 35, 40), (47, 25, 31), (120, 30, 30)}


def button(rect, label, fn, base=PIX_PANEL, hov=PIX_PANEL_HI, border=PIX_DIM, color=PIX_CREAM,
           font=None, enabled=True, bw=2):
    rect = pygame.Rect(rect)
    hover = enabled and rect.collidepoint(G.mouse)
    if base in _GOOD_BASE:
        fill, fill_h, brd, brd_h, tc, tc_h = PIX_ORANGE, PIX_GOLD, PIX_CREAM, PIX_CREAM, PIX_INK, PIX_INK
    elif base in _BAD_BASE:
        fill, fill_h, brd, brd_h, tc, tc_h = (130, 44, 52), (190, 58, 60), (236, 120, 110), PIX_CREAM, PIX_CREAM, PIX_CREAM
    else:
        fill, fill_h, brd, brd_h, tc, tc_h = base, hov, border, PIX_GOLD, color, PIX_GOLD
    if not enabled:
        fill, brd, tc = (28, 25, 36), (70, 65, 80), (120, 115, 130)
    cur_fill = fill_h if hover else fill
    draw_wavy_rect(rect, brd_h if hover else brd, cur_fill, max(2, bw), 0)
    text(label, font or F_SMALL, tc_h if hover else tc, rect.centerx, rect.centery, "center")
    if enabled:
        hits.append((rect, fn))
    return hover


def click_area(rect, fn):
    hits.append((pygame.Rect(rect), fn))


def field(rect, key, label="", masked=False, hint=""):
    rect = pygame.Rect(rect)
    if label:
        text(label, F_SMALL, PIX_DIM, rect.x, rect.y - 18)
    focused = G.focus == key
    draw_wavy_rect(rect, PIX_MINT if focused else PIX_DIM,
                   (43, 34, 61) if focused else (20, 16, 32), 2, 1.0)
    value = "*" * len(fields[key]) if masked else fields[key]
    if not value and not focused and hint:
        text(hint, F_SMALL, (110, 105, 128), rect.x + 10, rect.centery, "midleft")
    else:
        caret = "|" if focused and (pygame.time.get_ticks() // 450) % 2 == 0 else ""
        shown = value + caret
        while F_MED.size(shown)[0] > rect.width - 18 and len(shown) > 1:
            shown = shown[1:]
        text(shown, F_MED, PIX_CREAM, rect.x + 10, rect.centery, "midleft")
    click_area(rect, lambda k=key: set_focus(k))


def set_focus(k):
    if k in fields:
        G.focus = k
        try:
            pygame.key.set_text_input_rect(pygame.Rect(0, HEIGHT // 2, WIDTH, 40))
        except Exception:
            pass


# ============================================================
# Particle effects
# ============================================================
def particle(x, y, vx, vy, color, life=1.0, size=3):
    if len(particles) >= MAX_PARTICLES:
        return
    particles.append({"x": float(x), "y": float(y), "vx": float(vx), "vy": float(vy),
                      "color": tuple(color), "life": float(life), "size": int(size)})


def explosion(x, y, color=PIX_ORANGE, count=18, sound=True):
    if sound:
        snd("hit")
    count = min(int(count), max(0, MAX_PARTICLES - len(particles)))
    for _ in range(count):
        a = random.random() * math.tau
        speed = random.uniform(1.5, 7.0)
        particle(x, y, math.cos(a) * speed, math.sin(a) * speed,
                 color, random.uniform(0.55, 1.0), random.randint(2, 5))


def update_particles():
    alive = []
    for p in particles:
        p["x"] += p["vx"]
        p["y"] += p["vy"]
        p["vy"] += 0.035
        p["life"] -= 0.045
        if p["life"] <= 0:
            continue
        r = max(1, int(p["size"] * p["life"]))
        pygame.draw.rect(screen, p["color"], (int(p["x"]), int(p["y"]), r, r))
        alive.append(p)
    particles[:] = alive


def update_thrusters():
    alive = []
    for p in thrusters:
        p["x"] += p["vx"]
        p["y"] += p["vy"]
        p["life"] -= 0.08
        if p["life"] <= 0:
            continue
        r = max(1, int(p["size"] * p["life"]))
        c = (255, int(120 + 80 * p["life"]), 40)
        pygame.draw.rect(screen, c, (int(p["x"]), int(p["y"]), r, r))
        alive.append(p)
    thrusters[:] = alive


# ============================================================
# Sprites
# ============================================================
PLAYER_ROWS = [
    ".......W", ".......W", "......WW", "......WC", ".....OWC", ".....WWW", "..R..WWw", ".RR.OWWw",
    ".RRrOWWw", "RRRrrWWw", "RRrRrwWw", "RrRRr.Ww", "R.rr..Ew", "R....EEE", ".....E.E", "........",
]
ENEMY_ROWS = {
    1: ["L....", ".L.AA", "..AAA", ".AAEP", "AAAAA", "AaAaA", "A.AAA", "L.A..", "L...."],
    2: [".....", "..AAA", ".AAAA", "AAEEA", "AAAAA", ".aAAA", "..aAA", ".L.L.", "L...L"],
    3: ["....A", "...AA", "..AAA", ".AACC", "AAACC", "AaAAA", ".AaAA", "..AaA", "...aA"],
}
BOSS_ROWS = [
    "..........aA", ".........aAA", "L.......aAAA", "LL.....aAAAA", "LLL...aAAAAA", "LLLL.aAAAAAA",
    "LLLLAAAAAAAA", "LaLLAAAAAAAA", "LaLAAAAEEEAA", ".aAAAAAEPPEA", "..AAAAAEEEAA", "..aAAAAAAAAA",
    "...aAAAAAdAA", "....aAAAdddA", ".....aAAAddd", "......aAAAdd", ".......aaAAd", "..........aa",
]
ROCKET_ROWS = [
    "......WWWWW.....", "..F..WWWWWWR....", "FFFWWWWWWWWWRR..", "FFEWWWCCWWWWWRRR",
    "FFFWWWWWWWWWRR..", "..F..WWWWWWR....", "......WWWWW.....",
]
HEART_ROWS = [".XX.XX.", "XXXXXXX", "XXXXXXX", ".XXXXX.", "..XXX..", "...X..."]


def sprite_mirror(rows, pal, scale, mirror=True):
    surf = pygame.Surface((len(rows[0]) * (2 if mirror else 1) * scale, len(rows) * scale), pygame.SRCALPHA)
    for yy, row in enumerate(rows):
        full = row + row[::-1] if mirror else row
        for xx, ch in enumerate(full):
            c = pal.get(ch)
            if c:
                pygame.draw.rect(surf, c, (xx * scale, yy * scale, scale, scale))
    return surf


def ship_surface(sid):
    key = ("ship", sid)
    if key not in _pixel_cache:
        sk = SKINS.get(sid, SKINS[1])
        pal = {"W": sk["primary"], "w": shade(sk["primary"], 0.65), "R": sk["wing"], "r": shade(sk["wing"], 0.6),
               "C": PIX_GOLD, "O": PIX_INK, "E": PIX_ORANGE}
        _pixel_cache[key] = sprite_mirror(PLAYER_ROWS, pal, 3)
    return _pixel_cache[key]


def heart_surface(filled):
    key = ("heart", filled)
    if key not in _pixel_cache:
        _pixel_cache[key] = sprite_mirror(HEART_ROWS, {"X": PIX_RED if filled else (70, 62, 90)}, 3, mirror=False)
    return _pixel_cache[key]


def rocket_surface():
    key = ("rocket",)
    if key not in _pixel_cache:
        pal = {"W": PIX_CREAM, "F": PIX_ORANGE, "E": PIX_GOLD, "C": PIX_BLUE, "R": PIX_RED}
        _pixel_cache[key] = sprite_mirror(ROCKET_ROWS, pal, 3, mirror=False)
    return _pixel_cache[key]


def draw_ship(x, y, sid, upgrade=False, shield=False):
    s = ship_surface(sid)
    ox, oy = 3, 3
    if upgrade:
        glow = pygame.Surface((s.get_width() + 16, s.get_height() + 16), pygame.SRCALPHA)
        cx, cy = glow.get_width() // 2, glow.get_height() // 2
        pygame.draw.circle(glow, (255, 200, 64, 55), (cx, cy), max(s.get_width(), s.get_height()) // 2 + 7)
        screen.blit(glow, (int(x + ox - 8), int(y + oy - 8)))
    screen.blit(s, (int(x) + ox, int(y) + oy))
    if shield:
        t = pygame.time.get_ticks() * 0.005
        rr = 33 + int(math.sin(t) * 2)
        bub = pygame.Surface((rr * 2 + 12, rr * 2 + 12), pygame.SRCALPHA)
        c = (bub.get_width() // 2, bub.get_height() // 2)
        pygame.draw.circle(bub, (96, 214, 160, 45), c, rr)
        pygame.draw.circle(bub, (244, 233, 206, 220), c, rr, 2)
        screen.blit(bub, (int(x + 27) - c[0], int(y + 27) - c[1]))


def enemy_surface(kind):
    key = ("enemy", kind)
    if key not in _pixel_cache:
        if kind == 1:
            pal = {"A": PIX_RED, "a": shade(PIX_RED, 0.6), "E": PIX_CREAM, "P": PIX_INK, "L": PIX_GOLD}
        elif kind == 2:
            pal = {"A": (96, 170, 110), "a": (60, 115, 80), "E": PIX_CREAM, "P": PIX_INK, "L": PIX_GOLD}
        else:
            pal = {"A": PIX_PURPLE, "a": shade(PIX_PURPLE, 0.62), "C": PIX_RED}
        _pixel_cache[key] = sprite_mirror(ENEMY_ROWS.get(kind, ENEMY_ROWS[1]), pal, 5)
    return _pixel_cache[key]


def boss_surface(rage, bright):
    key = ("boss", rage, bright)
    if key not in _pixel_cache:
        body = (200, 40, 50) if rage else (130, 70, 190)
        pal = {"A": body, "a": shade(body, 0.6), "d": shade(body, 0.8), "L": (214, 150, 60),
               "E": (255, 210, 60) if bright else (200, 110, 40), "P": PIX_INK}
        _pixel_cache[key] = sprite_mirror(BOSS_ROWS, pal, 5)
    return _pixel_cache[key]


def draw_enemy(e):
    s = enemy_surface(e.get("type", 1))
    bob = int(math.sin((pygame.time.get_ticks() + int(e.get("seed", 0)) * 13) * 0.012) * 2)
    screen.blit(s, (int(e["x"]), int(e["y"] + bob)))


def draw_player_avatar(cx, cy, scale=1):
    x = int(cx - 32 * scale)
    y = int(cy - 40 * scale)
    s = max(2, int(scale))
    pygame.draw.rect(screen, PIX_INK, (x, y, 64 * s, 80 * s))
    pygame.draw.rect(screen, PIX_BLUE, (x + 4 * s, y + 4 * s, 56 * s, 72 * s), 2)
    pygame.draw.rect(screen, PIX_CREAM, (x + 22 * s, y + 10 * s, 20 * s, 20 * s))
    pygame.draw.rect(screen, PIX_CREAM, (x + 16 * s, y + 30 * s, 32 * s, 25 * s))
    pygame.draw.rect(screen, PIX_MINT, (x + 9 * s, y + 54 * s, 18 * s, 15 * s))
    pygame.draw.rect(screen, PIX_MINT, (x + 37 * s, y + 54 * s, 18 * s, 15 * s))


def draw_projectile_icon(rect, style):
    rect = pygame.Rect(rect)
    p = PROJECTILES.get(style, PROJECTILES[1])
    cx, cy = rect.centerx, rect.centery
    if style == 1:
        pygame.draw.circle(screen, p["accent"], (cx, cy + 4), 17)
        pygame.draw.circle(screen, p["main"], (cx, cy + 1), 13)
        pygame.draw.polygon(screen, p["accent"], [(cx - 5, cy - 12), (cx, cy - 28), (cx + 8, cy - 10)])
    elif style == 2:
        pygame.draw.circle(screen, p["main"], (cx, cy), 16)
        for a in range(0, 180, 45):
            rad = math.radians(a)
            dx, dy = int(math.cos(rad) * 17), int(math.sin(rad) * 17)
            pygame.draw.line(screen, p["accent"], (cx - dx, cy - dy), (cx + dx, cy + dy), 2)
    elif style == 3:
        pygame.draw.circle(screen, p["main"], (cx, cy), 17)
        pygame.draw.circle(screen, PIX_CREAM, (cx - 4, cy - 5), 4)
        pygame.draw.circle(screen, PIX_BLUE, (cx + 6, cy + 5), 4)
    elif style == 4:
        pts = [(cx - 8, cy - 20), (cx + 2, cy - 3), (cx - 5, cy - 3),
               (cx + 9, cy + 19), (cx + 2, cy + 2), (cx + 9, cy + 2)]
        pygame.draw.polygon(screen, p["accent"], pts)
    elif style == 5:
        pygame.draw.circle(screen, p["main"], (cx, cy), 16)
        pygame.draw.polygon(screen, p["accent"], [(cx - 10, cy + 7), (cx, cy - 11), (cx + 10, cy + 7)])
    else:
        for a in range(0, 360, 45):
            rad = math.radians(a)
            x1 = cx + int(math.cos(rad) * 15)
            y1 = cy + int(math.sin(rad) * 15)
            x2 = cx + int(math.cos(rad) * 23)
            y2 = cy + int(math.sin(rad) * 23)
            pygame.draw.line(screen, p["accent"], (x1, y1), (x2, y2), 2)
        pygame.draw.circle(screen, p["main"], (cx, cy), 13)


# ============================================================
# Player / World
# ============================================================
class Player:
    def __init__(self, name, skin, bt=1, bs=13, x=0, y=0):
        self.name = str(name)
        self.skin = int(skin) if int(skin) in SKINS else 1
        self.bt = 1
        self.bs = clamp(int(bs), 13, MAX_BULLET_SPEED)
        self.x, self.y = float(x), float(y)
        self.hp = 3
        self.alive = True
        self.connected = True
        self.inv = 0
        self.cool = FIRE_DELAY
        self.fire = False
        self.shield_frames = 0
        self.overdrive_frames = 0
        self.upgrade_flash = 0
        self.projectile_style = int(P.get("ps", 1)) if self.name == G.user else 1
        if self.projectile_style not in PROJECTILES:
            self.projectile_style = 1

    @property
    def weapon(self):
        return 1


class World:
    def __init__(self, diff, players, coop=False):
        self.diff = diff if diff in DIFFS else "NORMAL"
        self.players = players
        self.coop = bool(coop)
        self.bullets = []
        self.ebullets = []
        self.enemies = []
        self.powerups = []
        self.boss = None
        self.score = 0
        self.level = 1
        self.level_start = 0
        self.spawn_timer = 0
        self.coins_total = 0
        self.tick = 0
        self.state = "PLAYING"
        self.events = []
        self.flash_message = ""
        self.flash_timer = 0

    def emit(self, *ev):
        if ev:
            self.events.append(list(ev))

    def add_explosion(self, x, y, color, count=18, sound=True):
        if sound:
            snd("hit")
        explosion(x, y, color, count, False)
        if self.coop:
            self.events.append(["ex", x, y, list(color), int(count), False])

    def spawn_powerup(self, x, y):
        if random.random() > 0.43:
            return
        kind = random.choices(["HP", "SHIELD", "UPGRADE"], weights=[0.38, 0.34, 0.28], k=1)[0]
        self.powerups.append({"x": float(x), "y": float(y), "kind": kind, "vx": 0.0})

    def fire(self, p):
        style = p.projectile_style if p.projectile_style in PROJECTILES else 1
        count = bullet_count_for_level(self.level)
        speed = p.bs + (2 if p.overdrive_frames > 0 else 0)
        speed = clamp(speed, 13, MAX_BULLET_SPEED)
        cx, cy = p.x + 25, p.y
        spread = {1: [0.0], 2: [-0.11, 0.11], 3: [-0.18, 0.0, 0.18], 5: [-0.42, -0.21, -0.07, 0.07, 0.21]}[count]
        for a in spread:
            self.bullets.append({
                "x": float(cx - 7), "y": float(cy),
                "vx": float(speed * math.sin(a)), "vy": float(-speed * math.cos(a)),
                "w": 14 if count >= 5 else 11, "h": 14 if style in (1, 3, 5, 6) else 22,
                "big": int(count >= 5), "style": style,
            })
        snd("fire2" if count >= 3 else "fire")

    def hurt(self, p, color=PIX_RED, count=24):
        if not p.alive or p.inv > 0:
            return
        if p.shield_frames > 0:
            p.inv = 12
            self.add_explosion(p.x + 25, p.y + 25, PIX_BLUE, 8, False)
            snd("shield")
            return
        p.hp -= 1
        p.inv = 90
        self.add_explosion(p.x + 25, p.y + 25, color, count, True)
        if p.hp <= 0:
            p.alive = False
            p.fire = False

    def grant_powerup(self, p, kind):
        if kind == "HP":
            old = p.hp
            p.hp = min(MAX_HP, p.hp + 2)
            self.flash_message = "HỒI MÁU +%d" % (p.hp - old)
            self.flash_timer = 80
            snd("power")
        elif kind == "SHIELD":
            p.shield_frames = max(p.shield_frames, SHIELD_FRAMES)
            p.inv = max(p.inv, 40)
            self.flash_message = "KHIÊN BẢO VỆ"
            self.flash_timer = 100
            snd("shield")
        elif kind == "UPGRADE":
            p.overdrive_frames = max(p.overdrive_frames, OVERDRIVE_FRAMES)
            p.upgrade_flash = UPGRADE_FLASH_FRAMES
            self.flash_message = "THĂNG CẤP HỎA LỰC"
            self.flash_timer = 110
            snd("upgrade")

    def spawn_enemy(self):
        d = DIFFS[self.diff]
        count = len(self.enemies)
        max_enemies = min(58, 14 + self.level // 2 + bullet_count_for_level(self.level) * 4)
        if count >= max_enemies:
            return
        side_prob = 0.18 + min(0.38, self.level * 0.006)
        if random.random() < side_prob:
            from_left = random.random() < 0.5
            x = -45.0 if from_left else WIDTH + 5.0
            y = random.uniform(85, HEIGHT * 0.62)
            vx = random.uniform(2.3, 4.2) * (1 if from_left else -1)
            vy = random.uniform(0.7, 1.6) * DIFFS[self.diff]["speed_mod"]
            self.enemies.append({"x": x, "y": y, "vx": vx, "vy": vy, "path": "side",
                                 "seed": random.randint(0, 10000), "type": random.choice([1, 2, 3]),
                                 "life": 0})
        else:
            self.enemies.append({
                "x": random.uniform(45, WIDTH - 90), "y": -45.0,
                "vx": random.uniform(-0.7, 0.7), "vy": random.uniform(1.8, 3.2) * d["speed_mod"],
                "path": "top", "seed": random.randint(0, 10000), "type": random.choice([1, 2, 3]), "life": 0,
            })

    def spawn_boss(self):
        hp = 170 + self.level * 58
        self.boss = {"x": WIDTH / 2 - 70.0, "y": -120.0, "hp": hp, "max_hp": hp,
                     "vx": 2.2 + self.level * 0.01, "shoot": 0, "phase": 0.0}
        snd("boss")

    def kill_boss(self):
        b = self.boss
        if not b:
            return
        self.add_explosion(b["x"] + 70, b["y"] + 55, PIX_GOLD, 70, True)
        self.coins_total += int(120 * self.level * DIFFS[self.diff]["coin_mod"])
        self.score += 100
        self.boss = None
        self.enemies.clear()
        self.ebullets.clear()
        self.level_start = self.score
        if self.level >= MAX_LEVELS:
            self.state = "VICTORY"
            self.flash_message = "PHÁ ĐẢO 50 MÀN!"
            self.flash_timer = 180
            return
        old_tier = bullet_count_for_level(self.level)
        self.level += 1
        new_tier = bullet_count_for_level(self.level)
        self.flash_message = "VƯỢT MÀN %d" % (self.level - 1)
        self.flash_timer = 120
        if new_tier != old_tier:
            for p in self.players:
                p.upgrade_flash = UPGRADE_FLASH_FRAMES
            self.flash_message = "NÂNG ĐẠN → %d TIA" % new_tier
            self.flash_timer = 150
            snd("upgrade")
        for p in self.players:
            if p.connected and not p.alive:
                p.alive, p.hp, p.inv = True, 2, 120

    def step(self):
        d = DIFFS[self.diff]
        self.tick += 1
        if self.flash_timer > 0:
            self.flash_timer -= 1
        for p in self.players:
            p.inv = max(0, p.inv - 1)
            p.shield_frames = max(0, p.shield_frames - 1)
            p.overdrive_frames = max(0, p.overdrive_frames - 1)
            p.upgrade_flash = max(0, p.upgrade_flash - 1)
            p.cool += 1
            if p.alive and p.fire and p.cool >= max(3, FIRE_DELAY - (1 if p.overdrive_frames else 0)):
                p.cool = 0
                self.fire(p)

        actors = [(p, pygame.Rect(int(p.x) + 8, int(p.y) + 7, 38, 38))
                  for p in self.players if p.alive and p.connected]

        if self.boss is None and self.state == "PLAYING" and (self.score - self.level_start) >= SCORE_PER_LEVEL:
            self.spawn_boss()

        if self.boss:
            b = self.boss
            if b["y"] < 55:
                b["y"] += 2.2
            else:
                b["x"] += b["vx"]
                b["phase"] += 0.025
                if b["x"] <= 10 or b["x"] + 140 >= WIDTH - 10:
                    b["vx"] *= -1
                    b["x"] = clamp(b["x"], 10, WIDTH - 150)
            b["shoot"] += 1
            interval = max(12, 42 - self.level // 2)
            if b["shoot"] >= interval:
                b["shoot"] = 0
                bottom = b["y"] + 84
                for dx in (40, 68, 96):
                    self.ebullets.append({"x": b["x"] + dx, "y": bottom,
                                          "vx": math.sin(b["phase"] + dx) * 1.3,
                                          "vy": 5.5 + self.level * 0.035})

        if self.boss is None:
            self.spawn_timer += 1
            tier = bullet_count_for_level(self.level)
            base = 40 - self.level * 0.38 - tier * 2.5
            rate = max(10, int(base * d["spawn_mod"]))
            if self.spawn_timer >= rate:
                self.spawn_timer = 0
                self.spawn_enemy()
                if tier >= 3 and random.random() < 0.18:
                    self.spawn_enemy()
                if tier >= 5 and random.random() < 0.22:
                    self.spawn_enemy()

        alive_enemies = []
        for e in self.enemies:
            e["life"] += 1
            if e["path"] == "side":
                e["x"] += e["vx"]
                e["y"] += e["vy"] + math.sin(e["life"] * 0.08 + e["seed"]) * 1.0
                if e["x"] < -80 or e["x"] > WIDTH + 40 or e["y"] > HEIGHT + 50:
                    continue
            else:
                e["x"] += e["vx"] + math.sin(e["life"] * 0.035 + e["seed"]) * 0.55
                e["y"] += e["vy"]
                if e["y"] > HEIGHT + 50:
                    continue
            er = pygame.Rect(int(e["x"]), int(e["y"]), 50, 42)
            hit_player = False
            for p, pr in actors:
                if pr.colliderect(er):
                    self.hurt(p, PIX_RED, 20)
                    hit_player = True
                    break
            if not hit_player:
                alive_enemies.append(e)
        self.enemies = alive_enemies

        eb_keep = []
        for eb in self.ebullets:
            eb["x"] += eb.get("vx", 0)
            eb["y"] += eb.get("vy", 7)
            if eb["y"] > HEIGHT + 30 or eb["x"] < -20 or eb["x"] > WIDTH + 20:
                continue
            r = pygame.Rect(int(eb["x"]), int(eb["y"]), 10, 20)
            hit = False
            for p, pr in actors:
                if pr.colliderect(r):
                    self.hurt(p)
                    hit = True
                    break
            if not hit:
                eb_keep.append(eb)
        self.ebullets = eb_keep

        bullet_keep = []
        for bl in self.bullets:
            bl["x"] += bl["vx"]
            bl["y"] += bl["vy"]
            if bl["y"] < -40 or bl["x"] < -50 or bl["x"] > WIDTH + 50:
                continue
            br = pygame.Rect(int(bl["x"]), int(bl["y"]), int(bl["w"]), int(bl["h"]))
            if self.boss and br.colliderect(pygame.Rect(int(self.boss["x"]), int(self.boss["y"]), 140, 90)):
                damage = 10 + (5 if bl.get("big") else 0)
                self.boss["hp"] -= damage
                col = PROJECTILES.get(bl.get("style", 1), PROJECTILES[1])["main"]
                explosion(bl["x"], bl["y"], col, 3, False)
                if self.boss["hp"] <= 0:
                    self.kill_boss()
                continue
            target = None
            for e in self.enemies:
                if br.colliderect(pygame.Rect(int(e["x"]), int(e["y"]), 50, 42)):
                    target = e
                    break
            if target:
                try:
                    self.enemies.remove(target)
                except ValueError:
                    pass
                self.score += 15
                self.coins_total += max(1, int(5 * d["coin_mod"]))
                col = {1: PIX_ORANGE, 2: PIX_BLUE, 3: PIX_MINT}.get(target["type"], PIX_PINK)
                explosion(target["x"] + 20, target["y"] + 20, col, 14, True)
                self.spawn_powerup(target["x"] + 20, target["y"] + 20)
                continue
            bullet_keep.append(bl)
        self.bullets = bullet_keep

        pu_keep = []
        for pu in self.powerups:
            pu["y"] += 1.8
            pu["x"] += math.sin((self.tick + int(pu["y"])) * 0.08) * 0.55
            if pu["y"] > HEIGHT + 30:
                continue
            r = pygame.Rect(int(pu["x"]), int(pu["y"]), 28, 28)
            taken = False
            for p, pr in actors:
                if pr.colliderect(r):
                    self.grant_powerup(p, pu["kind"])
                    taken = True
                    break
            if not taken:
                pu_keep.append(pu)
        self.powerups = pu_keep

        if not any(p.alive and p.connected for p in self.players):
            self.state = "GAME_OVER"

    def snapshot(self):
        s = {
            "k": "st",
            "p": [],
            "e": [[round(e["x"]), round(e["y"]), int(e.get("type", 1)), int(e.get("seed", 0)),
                   e.get("path", "top")] for e in self.enemies],
            "b": [[round(b["x"]), round(b["y"]), int(b.get("w", 10)), int(b.get("h", 20)),
                   int(b.get("big", 0)), int(b.get("style", 1))] for b in self.bullets],
            "eb": [[round(e["x"]), round(e["y"]), round(e.get("vx", 0), 2), round(e.get("vy", 7), 2)] for e in self.ebullets],
            "pu": [[round(p["x"]), round(p["y"]), p["kind"]] for p in self.powerups],
            "bo": [round(self.boss["x"]), round(self.boss["y"]), int(self.boss["hp"]), int(self.boss["max_hp"])] if self.boss else None,
            "sc": self.score, "lv": self.level, "co": self.coins_total, "ev": self.events, "stt": self.state,
            "msg": self.flash_message, "mt": self.flash_timer,
        }
        for p in self.players:
            s["p"].append([
                round(p.x), round(p.y), int(p.hp), int(p.skin), int(p.alive), int(p.inv), int(p.connected),
                int(p.overdrive_frames), int(p.shield_frames), int(p.projectile_style), int(p.upgrade_flash)
            ])
        self.events = []
        return s

    def apply_snapshot(self, s, local_idx):
        if not isinstance(s, dict) or not isinstance(s.get("p"), list):
            raise ValueError("Snapshot không hợp lệ")
        rows = s.get("p", [])
        for i, row in enumerate(rows[:len(self.players)]):
            if not isinstance(row, (list, tuple)) or len(row) < 8:
                continue
            p = self.players[i]
            if i != local_idx:
                p.x, p.y = float(row[0]), float(row[1])
                p.skin = int(row[3]) if int(row[3]) in SKINS else 1
            p.hp = int(row[2])
            p.alive = bool(row[4])
            p.inv = int(row[5])
            p.connected = bool(row[6])
            if len(row) >= 8:
                p.overdrive_frames = max(0, int(row[7]))
            if len(row) >= 9:
                p.shield_frames = max(0, int(row[8]))
            if len(row) >= 10:
                ps = int(row[9])
                p.projectile_style = ps if ps in PROJECTILES else 1
            if len(row) >= 11:
                p.upgrade_flash = max(0, int(row[10]))
        self.enemies = []
        for e in s.get("e", []):
            if len(e) >= 4:
                self.enemies.append({"x": e[0], "y": e[1], "type": e[2], "seed": e[3],
                                     "path": e[4] if len(e) >= 5 else "top", "vx": 0, "vy": 0, "life": 0})
        self.bullets = []
        for b in s.get("b", []):
            self.bullets.append({"x": b[0], "y": b[1], "w": b[2], "h": b[3], "big": b[4],
                                 "style": b[5] if len(b) >= 6 and b[5] in PROJECTILES else 1,
                                 "vx": 0, "vy": 0})
        self.ebullets = []
        for e in s.get("eb", []):
            self.ebullets.append({"x": e[0], "y": e[1], "vx": e[2] if len(e) > 2 else 0, "vy": e[3] if len(e) > 3 else 7})
        self.powerups = [{"x": p[0], "y": p[1], "kind": p[2]} for p in s.get("pu", []) if len(p) >= 3]
        bo = s.get("bo")
        self.boss = {"x": bo[0], "y": bo[1], "hp": bo[2], "max_hp": bo[3], "vx": 0, "shoot": 0, "phase": 0} if bo else None
        self.score = int(s.get("sc", self.score))
        self.level = int(s.get("lv", self.level))
        self.coins_total = int(s.get("co", self.coins_total))
        self.state = str(s.get("stt", self.state))
        self.flash_message = str(s.get("msg", ""))
        self.flash_timer = int(s.get("mt", 0))
        for ev in s.get("ev", []):
            if not isinstance(ev, list) or not ev:
                continue
            if ev[0] == "ex" and len(ev) >= 5:
                explosion(ev[1], ev[2], ev[3], int(ev[4]), False)


# ============================================================
# Match / input
# ============================================================
def spawn_pos(idx, total):
    return WIDTH // 2 - 25 + (idx - (total - 1) / 2) * 90, HEIGHT - 100


def begin_match(world, mode):
    G.W = world
    G.mode = mode
    G.credited = 0
    G.submitted = False
    G.got_snapshot = mode != "guest"
    particles.clear()
    thrusters.clear()
    G.state = "PLAYING"
    G.popup = False
    G.focus = None


def start_solo():
    x, y = spawn_pos(0, 1)
    begin_match(World(G.difficulty, [Player(G.user or "Khách", P["skin"], 1, P["bs"], x, y)], False), "solo")


def start_coop(role, partner):
    G.in_room = True
    G.partner = partner
    G.invite = None
    x0, y0 = spawn_pos(0, 2)
    x1, y1 = spawn_pos(1, 2)
    if role == "host":
        a = Player(G.user, P["skin"], 1, P["bs"], x0, y0)
        b = Player(partner, 1, 1, 13, x1, y1)
        a.inv, b.inv = 60, 120
    else:
        a = Player(partner, 1, 1, 13, x0, y0)
        b = Player(G.user, P["skin"], 1, P["bs"], x1, y1)
        a.inv, b.inv = 60, 120
    begin_match(World(G.difficulty, [a, b], True), role)
    toast("Vào phòng với %s!" % partner)


def leave_match():
    if G.W is not None and not G.submitted and G.W.score > 0:
        submit_score()
    if G.in_room:
        net_send({"t": "room_leave"})
    G.in_room = False
    G.W = None


def submit_score():
    if G.W is None or G.submitted:
        return
    G.submitted = True
    sc = max(0, int(G.W.score))
    P["hs"] = max(P["hs"], sc)
    net_send({"t": "score", "score": sc})
    mark_dirty()
    send_save()


def end_match(result):
    G.state = result
    if not G.submitted:
        submit_score()


def handle_room_msg(d):
    w = G.W
    if w is None or not isinstance(d, dict):
        return
    k = d.get("k")
    if k == "in" and G.mode == "host" and len(w.players) > 1:
        g = w.players[1]
        try:
            g.x = clamp(float(d.get("x", g.x)), 0, WIDTH - 55)
            g.y = clamp(float(d.get("y", g.y)), 0, HEIGHT - 55)
            g.fire = bool(d.get("f"))
            g.skin = int(d.get("s", 1)) if int(d.get("s", 1)) in SKINS else 1
            ps = int(d.get("ps", 1))
            g.projectile_style = ps if ps in PROJECTILES else 1
            g.bs = clamp(int(d.get("bs", 13)), 13, MAX_BULLET_SPEED)
        except (TypeError, ValueError):
            return
    elif k == "st" and G.mode == "guest":
        try:
            w.apply_snapshot(d, 1)
            G.got_snapshot = True
        except (KeyError, IndexError, TypeError, ValueError):
            return


def handle_room_end():
    G.in_room = False
    toast("Đồng đội đã rời phòng.", False)
    w = G.W
    if w is None:
        return
    if G.mode == "host":
        w.coop = False
        if len(w.players) > 1:
            w.players[1].connected = False
            w.players[1].alive = False
        G.mode = "solo"
    else:
        leave_match()
        set_state("MENU")


def read_input(p):
    k = pygame.key.get_pressed()
    dx = int(bool(k[pygame.K_RIGHT] or k[pygame.K_d])) - int(bool(k[pygame.K_LEFT] or k[pygame.K_a]))
    dy = int(bool(k[pygame.K_DOWN] or k[pygame.K_s])) - int(bool(k[pygame.K_UP] or k[pygame.K_w]))
    fire = bool(pygame.mouse.get_pressed()[0] or k[pygame.K_j] or k[pygame.K_k] or k[pygame.K_SPACE])
    p.x = clamp(p.x + dx * PLAYER_SPEED, 0, WIDTH - 55)
    p.y = clamp(p.y + dy * PLAYER_SPEED, 0, HEIGHT - 55)
    p.fire = fire


def update_play():
    w = G.W
    if w is None:
        return
    li = 1 if G.mode == "guest" else 0
    if li >= len(w.players):
        return
    me = w.players[li]
    if me.alive:
        read_input(me)
    else:
        me.fire = False
    for p in w.players:
        if p.alive and p.connected and len(thrusters) < MAX_THRUSTERS:
            thrusters.append({"x": p.x + 25, "y": p.y + 53, "vx": random.uniform(-0.6, 0.6),
                              "vy": random.uniform(2.5, 5.0), "size": random.randint(2, 5), "life": 1.0})

    delta = w.coins_total - G.credited
    if delta > 0:
        P["coins"] += delta
        G.credited = w.coins_total
        mark_dirty()

    if G.mode == "guest":
        if G.tick % 2 == 0:
            net_send({"t": "room_msg", "d": {"k": "in", "x": round(me.x), "y": round(me.y), "f": int(me.fire),
                                              "s": int(P["skin"]), "bs": int(P["bs"]), "ps": int(P.get("ps", 1))}},
                     reliable=False)
        if w.state != "PLAYING":
            end_match(w.state)
        return

    w.step()
    if G.mode == "host" and w.coop and (w.tick % 2 == 0 or w.state != "PLAYING"):
        net_send({"t": "room_msg", "d": w.snapshot()}, reliable=(w.state != "PLAYING"))
    delta = w.coins_total - G.credited
    if delta > 0:
        P["coins"] += delta
        G.credited = w.coins_total
        mark_dirty()
    if w.state != "PLAYING":
        end_match(w.state)


# ============================================================
# Menu actions
# ============================================================
def buy_skin(sid):
    sk = SKINS[sid]
    if sid in P["unlocked"]:
        P["skin"] = sid
        snd("power")
        return
    if P["coins"] < sk["price"]:
        toast("Không đủ xu!", False)
        return
    P["coins"] -= sk["price"]
    P["unlocked"].add(sid)
    P["skin"] = sid
    mark_dirty()
    send_save()
    snd("upgrade")


def choose_projectile(style):
    if style not in PROJECTILES:
        return
    P["ps"] = style
    save_config()
    if G.W is not None:
        li = 1 if G.mode == "guest" else 0
        if li < len(G.W.players):
            G.W.players[li].projectile_style = style
    toast("Đã chọn %s" % PROJECTILES[style]["name"])
    snd("power")


def add_friend():
    name = fields["friend"].strip()
    if not name:
        toast("Nhập tên tài khoản!", False)
        return
    net_send({"t": "friend_add", "name": name})
    fields["friend"] = ""


def invite_friend(name):
    net_send({"t": "invite", "name": name})


def accept_invite():
    if G.invite:
        net_send({"t": "invite_accept", "from": G.invite["from"]})
        G.invite = None


def decline_invite():
    if G.invite:
        net_send({"t": "invite_decline"})
        G.invite = None


def send_chat():
    msg = fields["chat"].strip()[:FIELD_MAX["chat"]]
    if not msg:
        return
    if G.chat_tab == "GLOBAL":
        net_send({"t": "chat_global", "msg": msg})
    else:
        if not G.chat_target:
            toast("Chọn bạn để chat!", False)
            return
        net_send({"t": "chat_private", "to": G.chat_target, "msg": msg})
    fields["chat"] = ""


def toggle_sound():
    G.sound_on = not G.sound_on


def logout():
    leave_match()
    if G.user:
        send_save()
    go_login("")


def quit_game():
    leave_match()
    if G.user:
        send_save()
    if G.net:
        G.net.close()
    pygame.event.post(pygame.event.Event(pygame.QUIT))


# ============================================================
# State / screens
# ============================================================
def set_state(s):
    G.state = s
    G.popup = False
    G.scroll = 0
    G.focus = {"LOGIN": "user" if not fields["user"] else "pass", "FRIENDS": "friend", "CHAT": "chat"}.get(s)
    if s in ("FRIENDS", "BOARD", "CHAT"):
        refresh_social()
    elif s == "MENU":
        net_send({"t": "friends_get"})


def back_button(label="QUAY LẠI MENU", y=None):
    button(pygame.Rect(50, y if y is not None else HEIGHT - 55, WIDTH - 100, 36), label,
           lambda: set_state("MENU"), base=(47, 25, 31), hov=(71, 34, 44), border=PIX_RED, color=(255, 195, 185))


def draw_stars():
    screen.fill(PIX_BG)
    if not hasattr(draw_stars, "stars"):
        draw_stars.stars = []
        for _ in range(125):
            layer = random.choice([1, 1, 1, 2, 3])
            draw_stars.stars.append([random.randrange(WIDTH), random.randrange(HEIGHT), layer, random.randrange(150, 255)])
    for st in draw_stars.stars:
        st[1] += 0.45 * st[2]
        if st[1] >= HEIGHT:
            st[1] = 0
            st[0] = random.randrange(WIDTH)
        base = PIX_GOLD if st[2] == 3 else PIX_CREAM if st[2] == 2 else (110, 104, 140)
        c = shade(base, 0.55 + 0.45 * st[3] / 255)
        pygame.draw.rect(screen, c, (int(st[0]), int(st[1]), st[2], st[2]))


def draw_splash():
    G.splash += 1
    t = G.splash
    screen.fill(PIX_BG)
    cx, cy = WIDTH // 2, HEIGHT // 2 - 70
    bob = int(math.sin(t * 0.12) * 5)
    big = pygame.transform.scale(ship_surface(1), (144, 144))
    screen.blit(big, (cx - 72, cy - 72 + bob))
    for dx in (-12, 12):
        pygame.draw.rect(screen, PIX_ORANGE, (cx + dx - 4, cy + 72 + bob, 8, 10 + (t // 3) % 3 * 4))
    text("ĐẠI CHIẾN", F_LARGE, PIX_CREAM, cx, cy + 112, "midtop")
    text("KHÔNG GIAN", F_TITLE, PIX_GOLD, cx, cy + 146, "midtop")
    text("NAM SEX • 50 MÀN", F_TINY, PIX_DIM, cx, cy + 184, "midtop")
    seg_n, seg_w, gap = 20, 11, 3
    bx = cx - (seg_n * (seg_w + gap) - gap) // 2
    filled = int(seg_n * min(1.0, t / 90))
    for i in range(seg_n):
        pygame.draw.rect(screen, PIX_GOLD if i < filled else PIX_PANEL_HI, (bx + i * (seg_w + gap), cy + 215, seg_w, 14))
    if t >= 90:
        set_state("LOGIN")


def draw_login():
    draw_wavy_rect(pygame.Rect(38, 45, WIDTH - 76, 600), PIX_MINT, (25, 19, 39))
    title = "ĐĂNG NHẬP" if G.auth_mode == "LOGIN" else "ĐĂNG KÝ"
    text(title, F_LARGE, PIX_MINT, WIDTH // 2, 80, "midtop")
    if SERVER_V6 and SERVER_V6 != SERVER_V4:
        srv_line = "server | v4 %s | v6 %s" % (SERVER_V4, SERVER_V6)
        if F_TINY.size(srv_line)[0] > WIDTH - 90:
            srv_line = "UDP | IPv4 + IPv6 (2 server)"
    else:
        srv_line = "UDP | IPv4 + IPv6 | %s" % SERVER_V4
    text(srv_line, F_TINY, PIX_BLUE, WIDTH // 2, 123, "midtop")
    screen.blit(ship_surface(P["skin"]), (WIDTH // 2 - 24, 128))
    field(pygame.Rect(80, 185, 440, 44), "user", "Tên tài khoản", hint="3-16 chữ/số/_")
    field(pygame.Rect(80, 275, 440, 44), "pass", "Mật khẩu", masked=True)
    label = "ĐĂNG NHẬP" if G.auth_mode == "LOGIN" else "TẠO TÀI KHOẢN"
    button(pygame.Rect(80, 350, 440, 50), label, submit_auth, base=(37, 104, 78), hov=(48, 140, 100), border=PIX_MINT,
           font=F_MED, enabled=not G.connecting)

    def switch():
        G.auth_mode = "REGISTER" if G.auth_mode == "LOGIN" else "LOGIN"
        G.auth_msg = ""
    r = pygame.Rect(100, 420, 400, 34)
    text("Chưa có tài khoản? Đăng ký" if G.auth_mode == "LOGIN" else "Đã có tài khoản? Đăng nhập",
         F_SMALL, PIX_BLUE if r.collidepoint(G.mouse) else PIX_DIM, r.centerx, r.centery, "center")
    click_area(r, switch)
    if G.auth_msg:
        text(G.auth_msg, F_SMALL, G.auth_color, WIDTH // 2, 486, "midtop")
    text("TAB đổi ô • ENTER xác nhận", F_TINY, PIX_DIM, WIDTH // 2, 565, "midtop")
    # Hiện đường đang dùng + RTT nếu có
    if G.user and G.net and G.route:
        rtt_txt = " %.0fms" % (G.net.rtt * 1000) if G.net.rtt is not None else ""
        text("Đang dùng: %s%s" % (G.route, rtt_txt), F_TINY, PIX_MINT, WIDTH // 2, 600, "midtop")


def draw_profile_bar():
    draw_wavy_rect(pygame.Rect(196, 14, 208, 58), PIX_MINT, (28, 21, 43))
    draw_player_avatar(215, 26, 0.45)
    name = (G.user or "KHÁCH")[:12]
    text(name.upper(), F_SMALL, PIX_CREAM, 240, 24)
    text("Xu: %d" % P["coins"], F_TINY, PIX_GOLD, 240, 45)
    click_area(pygame.Rect(196, 14, 208, 58), lambda: set_state("PROFILE"))


def draw_menu_rocket():
    if not hasattr(draw_menu_rocket, "r"):
        draw_menu_rocket.r = {"x": -100.0, "y": HEIGHT // 2 - 20.0, "vx": 6.0, "vy": -1.2}
    r = draw_menu_rocket.r
    r["x"] += r["vx"]
    r["y"] += r["vy"]
    if r["x"] > WIDTH + 150:
        r["x"] = -150.0
        r["y"] = float(random.randint(HEIGHT // 2 - 60, HEIGHT // 2 + 60))
    if random.random() < 0.8 and len(particles) < MAX_PARTICLES - 4:
        particle(r["x"] - 6, r["y"] + 10 + random.uniform(-4, 4), -random.uniform(3, 6), random.uniform(-1, 1),
                 random.choice([PIX_ORANGE, PIX_GOLD]), 0.8, random.randint(2, 4))
    screen.blit(rocket_surface(), (int(r["x"]), int(r["y"])))


def badge(cx, cy, n):
    r = pygame.Rect(0, 0, 22, 20)
    r.center = (cx, cy)
    pygame.draw.rect(screen, PIX_INK, r.move(2, 2))
    pygame.draw.rect(screen, PIX_RED, r)
    pygame.draw.rect(screen, PIX_CREAM, r, 2)
    text(str(min(n, 99)), F_TINY, PIX_CREAM, r.centerx, r.centery, "center")


def draw_menu():
    text("ĐẠI CHIẾN KHÔNG GIAN", F_TITLE, PIX_GOLD, WIDTH // 2, 22, "midtop")
    pygame.draw.rect(screen, PIX_ORANGE, (WIDTH // 2 - 150, 58, 300, 3))

    d = DIFFS[G.difficulty]
    diff_rect = pygame.Rect(20, 80, 140, 45)
    hov = diff_rect.collidepoint(G.mouse)
    draw_wavy_rect(diff_rect, d["color"] if hov else PIX_DIM, PIX_PANEL_HI if hov else PIX_PANEL, 2)
    text("ĐỘ KHÓ", F_TINY, PIX_DIM, diff_rect.centerx, diff_rect.top + 5, "midtop")
    text(d["name"], F_MED, d["color"], diff_rect.centerx, diff_rect.top + 20, "midtop")
    click_area(diff_rect, lambda: set_state("DIFF"))

    pr = pygame.Rect(WIDTH // 2 - 100, 80, 200, 45)
    hov = pr.collidepoint(G.mouse)
    draw_wavy_rect(pr, PIX_GOLD if hov else PIX_DIM, PIX_PANEL_HI if hov else PIX_PANEL, 2)
    pygame.draw.rect(screen, PIX_CREAM, (pr.x + 16, pr.y + 9, 12, 12))
    pygame.draw.rect(screen, PIX_CREAM, (pr.x + 11, pr.y + 24, 22, 10))
    name = (G.user[:9] + "..") if len(G.user or "") > 9 else (G.user or "KHÁCH")
    text(name.upper(), F_SMALL, PIX_CREAM, pr.x + 42, pr.y + 4)
    text("Xu %d | KL %d" % (P["coins"], P["hs"]), F_TINY, PIX_GOLD, pr.x + 42, pr.y + 25)
    click_area(pr, lambda: set_state("PROFILE"))

    gear = pygame.Rect(WIDTH - 65, 80, 45, 45)
    hov = gear.collidepoint(G.mouse)
    draw_wavy_rect(gear, PIX_GOLD if hov else PIX_DIM, PIX_PANEL_HI if hov else PIX_PANEL, 2)
    for dy in (-7, 0, 7):
        pygame.draw.rect(screen, PIX_GOLD if hov else PIX_CREAM, (gear.centerx - 10, gear.centery + dy - 2, 20, 4))
    click_area(gear, lambda: setattr(G, "popup", not G.popup))

    draw_menu_rocket()
    bob = int(math.sin(pygame.time.get_ticks() * 0.004) * 4)
    ship = pygame.transform.scale(ship_surface(P["skin"]), (96, 96))
    sx, sy = WIDTH // 2 - 48, HEIGHT // 2 - 40 + bob
    for dx in (-8, 8):
        pygame.draw.rect(screen, random.choice([PIX_ORANGE, PIX_GOLD]), (WIDTH // 2 + dx - 3, sy + 90, 6, random.randint(8, 16)))
    screen.blit(ship, (sx, sy))
    plate = pygame.Rect(WIDTH // 2 - 60, HEIGHT // 2 + 86, 120, 6)
    pygame.draw.rect(screen, PIX_DIM, plate)
    pygame.draw.rect(screen, PIX_INK, plate.move(0, 6))

    nreq = len(G.friends["requests"])
    total_unread = sum(G.chat_unread.values()) + G.chat_badge_global
    button(pygame.Rect(20, HEIGHT - 165, 180, 40), "Bạn Bè (%d)" % len(G.friends["friends"]),
           lambda: set_state("FRIENDS"), border=PIX_BLUE)
    if nreq:
        badge(192, HEIGHT - 165, nreq)
    button(pygame.Rect(210, HEIGHT - 165, 180, 40), "Xếp Hạng", lambda: set_state("BOARD"), border=PIX_GOLD)
    button(pygame.Rect(400, HEIGHT - 165, 180, 40), "Chat", lambda: set_state("CHAT"), border=PIX_PURPLE)
    if total_unread:
        badge(572, HEIGHT - 165, total_unread)

    button(pygame.Rect(30, HEIGHT - 100, 130, 45), "Shop Skin", lambda: set_state("SHOP_SKIN"), border=PIX_PINK)
    button(pygame.Rect(WIDTH // 2 - 90, HEIGHT - 110, 180, 55), "BẮT ĐẦU", start_solo,
           base=(37, 104, 78), font=F_LARGE)
    button(pygame.Rect(WIDTH - 160, HEIGHT - 100, 130, 45), "Shop Vũ Khí",
           lambda: set_state("SHOP_PROJECTILE"), border=PIX_MINT)
    text("WASD/Mũi tên: bay | Space/J: bắn | ESC: dừng", F_TINY, PIX_DIM, WIDTH // 2, HEIGHT - 10, "midbottom")

    # Hiện route + RTT
    if G.net and G.route:
        rtt_txt = " %.0fms" % (G.net.rtt * 1000) if G.net.rtt is not None else ""
        text("%s%s" % (G.route, rtt_txt), F_TINY, PIX_MINT, WIDTH - 10, HEIGHT - 30, "topright")

    if G.popup:
        pop = pygame.Rect(WIDTH - 185, 132, 175, 135)
        click_area(pop, lambda: None)
        draw_wavy_rect(pop, PIX_GOLD, PIX_PANEL, 2)
        button(pygame.Rect(pop.x + 10, pop.y + 8, 155, 35), "Đổi Tài Khoản", logout)
        button(pygame.Rect(pop.x + 10, pop.y + 50, 155, 35), "Âm thanh: %s" % ("BẬT" if G.sound_on else "TẮT"),
               toggle_sound)
        button(pygame.Rect(pop.x + 10, pop.y + 92, 155, 35), "Thoát", quit_game, base=(120, 30, 30))


def draw_diff():
    draw_wavy_rect(pygame.Rect(40, 55, WIDTH - 80, HEIGHT - 110), PIX_GOLD, (28, 21, 40))
    text("CHỌN ĐỘ KHÓ", F_LARGE, PIX_GOLD, WIDTH // 2, 75, "midtop")
    for i, k in enumerate(("EASY", "NORMAL", "HARD")):
        d = DIFFS[k]
        r = pygame.Rect(68, 165 + i * 92, WIDTH - 136, 62)
        button(r, d["name"], lambda k=k: choose_diff(k), border=d["color"], color=d["color"], font=F_MED,
               bw=3 if G.difficulty == k else 2)
        text("Tốc độ x%.2f • quái x%.2f • xu x%.1f" % (d["speed_mod"], 1.0 / d["spawn_mod"], d["coin_mod"]),
             F_TINY, PIX_DIM, WIDTH // 2, r.bottom - 10, "center")
    back_button(y=HEIGHT - 48)


def choose_diff(k):
    if k in DIFFS:
        G.difficulty = k
        P["difficulty"] = k
        save_config()
        set_state("MENU")


def draw_shop_projectile():
    draw_wavy_rect(pygame.Rect(25, 25, WIDTH - 50, HEIGHT - 50), PIX_BLUE, (25, 19, 39))
    text("SHOP HÌNH ĐẠN", F_LARGE, PIX_BLUE, WIDTH // 2, 40, "midtop")
    text("Số tia tự tăng theo màn: 1 → 2 → 3 → 5", F_SMALL, PIX_CREAM, WIDTH // 2, 75, "midtop")
    text("Không còn mua số tia. Chỉ chọn loại hình đạn.", F_TINY, PIX_DIM, WIDTH // 2, 99, "midtop")
    for i, sid in enumerate(PROJECTILES):
        col = i % 2
        row = i // 2
        r = pygame.Rect(45 + col * 260, 130 + row * 105, 235, 88)
        active = sid == P.get("ps", 1)
        draw_wavy_rect(r, PIX_MINT if active else PIX_DIM, (44, 32, 60) if active else (30, 24, 46), 3 if active else 2)
        draw_projectile_icon(pygame.Rect(r.x + 15, r.y + 14, 54, 54), sid)
        text(PROJECTILES[sid]["name"], F_SMALL, PIX_GOLD if active else PIX_CREAM, r.x + 80, r.y + 8)
        text("ĐÃ CHỌN" if active else "CLICK ĐỂ CHỌN", F_TINY, PIX_MINT if active else PIX_DIM, r.x + 80, r.y + 28)
        for li_, ln_ in enumerate(wrap_text(PROJECTILES[sid]["desc"], F_TINY, r.width - 90)[:2]):
            text(ln_, F_TINY, PIX_DIM, r.x + 80, r.y + 46 + li_ * 15)
        click_area(r, lambda s=sid: choose_projectile(s))
    back_button(y=HEIGHT - 48)


def draw_shop_skin():
    draw_wavy_rect(pygame.Rect(25, 25, WIDTH - 50, HEIGHT - 50), PIX_PINK, (25, 19, 39))
    text("SHOP SKIN", F_LARGE, PIX_PINK, WIDTH // 2, 40, "midtop")
    text("XU: %d" % P["coins"], F_MED, PIX_GOLD, WIDTH // 2, 72, "midtop")
    for sid, sk in SKINS.items():
        y = 120 + (sid - 1) * 105
        r = pygame.Rect(40, y, WIDTH - 80, 88)
        active = sid == P["skin"]
        owned = sid in P["unlocked"]
        border = PIX_MINT if active else PIX_CREAM if owned else PIX_GOLD
        draw_wavy_rect(r, border, (35, 28, 50) if active else (26, 21, 38), 3 if active else 2)
        draw_ship(r.right - 80, r.y + 20, sid)
        text(sk["name"], F_SMALL, border, r.x + 16, r.y + 10)
        text("ĐANG DÙNG" if active else "SỞ HỮU" if owned else "GIÁ %d XU" % sk["price"],
             F_SMALL, PIX_MINT if owned else PIX_GOLD, r.x + 16, r.y + 35)
        text(sk["desc"], F_TINY, PIX_DIM, r.x + 16, r.y + 58)
        click_area(r, lambda s=sid: buy_skin(s))
    back_button(y=HEIGHT - 48)


def draw_profile():
    draw_wavy_rect(pygame.Rect(30, 30, WIDTH - 60, HEIGHT - 60), PIX_MINT, (25, 19, 39))
    text("THÔNG TIN CÁ NHÂN", F_LARGE, PIX_MINT, WIDTH // 2, 45, "midtop")
    draw_player_avatar(WIDTH // 2 - 32, 116, 1)
    text((G.user or "KHÁCH").upper(), F_LARGE, PIX_CREAM, WIDTH // 2, 205, "midtop")
    draw_wavy_rect(pygame.Rect(60, 245, WIDTH - 120, 270), PIX_BLUE, (30, 24, 45))
    rank = G.board.get("rank") or "-"
    rtt_row = "—"
    if G.net and G.route:
        rtt_row = "%s %s" % (G.route, "%.0fms" % (G.net.rtt * 1000) if G.net.rtt is not None else "")
    rows = [
        ("Tiền xu", P["coins"]), ("Kỷ lục", P["hs"]), ("Hạng", "#%s / %s" % (rank, G.board.get("total", "-"))),
        ("Skin", SKINS[P["skin"]]["name"]), ("Hình đạn", PROJECTILES[P.get("ps", 1)]["name"]),
        ("Tốc độ đạn", P["bs"]), ("Kết nối", rtt_row), ("Bạn bè", len(G.friends["friends"])),
    ]
    for i, (k, v) in enumerate(rows):
        yy = 262 + i * 31
        text(k, F_SMALL, PIX_DIM, 82, yy)
        text(v, F_SMALL, PIX_GOLD, WIDTH - 82, yy, "topright")
    back_button(y=HEIGHT - 48)


def draw_friends():
    draw_wavy_rect(pygame.Rect(25, 25, WIDTH - 50, HEIGHT - 50), PIX_BLUE, (25, 19, 39))
    text("BẠN BÈ", F_LARGE, PIX_MINT, WIDTH // 2, 40, "midtop")
    field(pygame.Rect(45, 100, 365, 42), "friend", "Thêm bạn", hint="Tên tài khoản")
    button(pygame.Rect(425, 100, 125, 42), "GỬI", add_friend, base=(37, 104, 78), hov=(48, 140, 100), border=PIX_MINT)
    y = 160
    reqs = G.friends.get("requests", [])
    text("LỜI MỜI (%d)" % len(reqs), F_SMALL, PIX_GOLD, 45, y)
    y += 27
    for name in reqs[:3]:
        r = pygame.Rect(45, y, 505, 35)
        draw_wavy_rect(r, PIX_DIM, (31, 24, 47), 1, 1)
        text(name, F_SMALL, PIX_CREAM, 55, r.centery, "midleft")
        button(pygame.Rect(r.right - 195, r.y + 4, 85, 27), "OK",
               lambda n=name: net_send({"t": "friend_accept", "name": n}), base=(37, 104, 78), border=PIX_MINT, font=F_TINY)
        button(pygame.Rect(r.right - 100, r.y + 4, 85, 27), "TỪ CHỐI",
               lambda n=name: net_send({"t": "friend_decline", "name": n}), base=(104, 35, 40), border=PIX_RED, font=F_TINY)
        y += 40
    y += 8
    friends = G.friends.get("friends", [])
    text("BẠN (%d)" % len(friends), F_SMALL, PIX_MINT, 45, y)
    y += 30
    area = pygame.Rect(45, y, 505, HEIGHT - y - 70)
    if not friends:
        text("Chưa có bạn. Hãy thêm bạn để chơi co-op!", F_SMALL, PIX_DIM, area.centerx, area.y + 20, "center")
    else:
        row_h = 48
        max_scroll = max(0, len(friends) * row_h - area.height)
        G.scroll = clamp(G.scroll, 0, max_scroll)
        old_clip = screen.get_clip()
        screen.set_clip(area)
        for i, f in enumerate(friends):
            if not isinstance(f, dict):
                continue
            ry = area.y + i * row_h - G.scroll
            r = pygame.Rect(area.x, ry, area.width, 40)
            if r.bottom < area.top or r.top > area.bottom:
                continue
            draw_wavy_rect(r, PIX_DIM, (29, 23, 44), 1, 0.8)
            online = bool(f.get("online"))
            pygame.draw.rect(screen, PIX_MINT if online else (100, 95, 110), (r.x + 8, r.centery - 4, 8, 8))
            text(str(f.get("name", "?")), F_SMALL, PIX_CREAM, r.x + 23, r.centery, "midleft")
            text(str(f.get("high_score", 0)), F_SMALL, PIX_GOLD, r.x + 190, r.centery, "midleft")
            chat_r = pygame.Rect(r.right - 210, r.y + 6, 85, 28)
            button(chat_r, "CHAT", lambda n=f.get("name", ""): open_private(n), base=(45, 50, 85), border=PIX_BLUE, font=F_TINY)
            play_r = pygame.Rect(r.right - 115, r.y + 6, 100, 28)
            button(play_r, "MỜI CHƠI", lambda n=f.get("name", ""): invite_friend(n),
                   base=(59, 42, 86), border=PIX_PURPLE, font=F_TINY, enabled=online and not G.in_room)
        screen.set_clip(old_clip)
    back_button(y=HEIGHT - 48)


def open_private(name):
    G.chat_tab = "PRIVATE"
    G.chat_target = str(name)
    G.chat_unread[G.chat_target] = 0
    set_state("CHAT")


def draw_board():
    draw_wavy_rect(pygame.Rect(25, 25, WIDTH - 50, HEIGHT - 50), PIX_GOLD, (25, 19, 39))
    text("BẢNG XẾP HẠNG", F_LARGE, PIX_GOLD, WIDTH // 2, 40, "midtop")
    button(pygame.Rect(45, 88, 245, 38), "BẠN BÈ", lambda: setattr(G, "board_tab", "FRIENDS"),
           base=(50, 41, 67) if G.board_tab == "FRIENDS" else PIX_PANEL,
           border=PIX_GOLD if G.board_tab == "FRIENDS" else PIX_DIM)
    button(pygame.Rect(310, 88, 245, 38), "TOÀN SERVER", lambda: setattr(G, "board_tab", "SERVER"),
           base=(50, 41, 67) if G.board_tab == "SERVER" else PIX_PANEL,
           border=PIX_GOLD if G.board_tab == "SERVER" else PIX_DIM)
    if G.board_tab == "FRIENDS":
        rows = [(f.get("name", "?"), int(f.get("high_score", 0))) for f in G.friends.get("friends", []) if isinstance(f, dict)]
        rows.append((G.user or "?", max(P["hs"], int(G.friends.get("me_score", 0)))))
        rows.sort(key=lambda x: (-x[1], x[0]))
    else:
        rows = [(r.get("name", "?"), int(r.get("score", 0))) for r in G.board.get("top", []) if isinstance(r, dict)]
    area = pygame.Rect(45, 145, 510, HEIGHT - 145 - 75)
    row_h = 42
    max_scroll = max(0, len(rows) * row_h - area.height)
    G.scroll = clamp(G.scroll, 0, max_scroll)
    old_clip = screen.get_clip()
    screen.set_clip(area)
    for i, (name, sc) in enumerate(rows):
        r = pygame.Rect(area.x, area.y + i * row_h - G.scroll, area.width, 34)
        if r.bottom < area.top or r.top > area.bottom:
            continue
        me = name == G.user
        draw_wavy_rect(r, PIX_GOLD if me else PIX_DIM, (54, 45, 20) if me else (29, 23, 44), 1, 0.8)
        text("#%d" % (i + 1), F_SMALL, PIX_GOLD if i < 3 else PIX_DIM, r.x + 10, r.centery, "midleft")
        text(name + (" (bạn)" if me else ""), F_SMALL, PIX_CREAM, r.x + 62, r.centery, "midleft")
        text(sc, F_MED, PIX_GOLD, r.right - 12, r.centery, "midright")
    screen.set_clip(old_clip)
    back_button(y=HEIGHT - 48)


def draw_chat():
    draw_wavy_rect(pygame.Rect(20, 20, WIDTH - 40, HEIGHT - 40), PIX_BLUE, (25, 19, 39))
    text("PHÒNG CHAT", F_LARGE, PIX_MINT, WIDTH // 2, 30, "midtop")
    button(pygame.Rect(30, 70, 130, 34), "TỔNG", lambda: switch_chat("GLOBAL"),
           base=(47, 70, 65) if G.chat_tab == "GLOBAL" else PIX_PANEL, border=PIX_MINT)
    button(pygame.Rect(170, 70, 130, 34), "RIÊNG", lambda: switch_chat("PRIVATE"),
           base=(47, 70, 65) if G.chat_tab == "PRIVATE" else PIX_PANEL, border=PIX_MINT)
    msg_top = 114
    if G.chat_tab == "PRIVATE":
        text("BẠN:", F_TINY, PIX_DIM, 30, 111)
        x = 65
        for f in G.friends.get("friends", [])[:7]:
            if not isinstance(f, dict):
                continue
            name = str(f.get("name", "?"))
            w = max(68, F_TINY.size(name)[0] + 18)
            if x + w > WIDTH - 30:
                break
            button(pygame.Rect(x, 106, w, 25), name, lambda n=name: select_chat_target(n),
                   base=(37, 104, 78) if G.chat_target == name else PIX_PANEL,
                   border=PIX_MINT if G.chat_target == name else PIX_DIM, font=F_TINY)
            x += w + 6
        msg_top = 140
    area = pygame.Rect(30, msg_top, WIDTH - 60, HEIGHT - msg_top - 120)
    draw_wavy_rect(area, PIX_DIM, (10, 8, 16), 1, 0.8)
    if G.chat_tab == "GLOBAL":
        msgs = G.chat_global
    else:
        msgs = G.chat_private.get(G.chat_target, []) if G.chat_target else []
    lines = []
    for e in msgs:
        who, msg = str(e.get("from", "?")), str(e.get("msg", ""))
        words = msg.split()
        cur = who + ": "
        max_chars = max(20, (area.width - 20) // max(1, F_SMALL.size('M')[0]))
        wrap = []
        for word in words:
            if len(cur) + len(word) + 1 > max_chars:
                wrap.append(cur)
                cur = "    " + word
            else:
                cur += (" " if cur and not cur.endswith(" ") else "") + word
        wrap.append(cur)
        lines.extend([(who, ln) for ln in wrap])
    line_h = 19
    total_h = len(lines) * line_h + 12
    max_scroll = max(0, total_h - area.height + 6)
    if not hasattr(G, "chat_scroll"):
        G.chat_scroll = 0
    G.chat_scroll = clamp(G.chat_scroll, 0, max_scroll)
    y = area.bottom - 8 - total_h + G.chat_scroll
    old_clip = screen.get_clip()
    screen.set_clip(area)
    for who, line in lines:
        text(line, F_SMALL, PIX_MINT if who == G.user else PIX_CREAM, area.x + 8, y)
        y += line_h
    screen.set_clip(old_clip)
    field(pygame.Rect(30, HEIGHT - 82, WIDTH - 120, 40), "chat", hint="Nhập tin nhắn...")
    button(pygame.Rect(WIDTH - 80, HEIGHT - 82, 50, 40), "GỬI", send_chat, base=(37, 104, 78), border=PIX_MINT, font=F_SMALL)
    back_button(y=HEIGHT - 40)


def switch_chat(k):
    G.chat_tab = k
    G.chat_badge_global = 0 if k == "GLOBAL" else G.chat_badge_global
    if k == "PRIVATE" and G.chat_target:
        G.chat_unread[G.chat_target] = 0
    G.chat_scroll = 0


def select_chat_target(n):
    G.chat_target = n
    G.chat_unread[n] = 0
    G.chat_scroll = 0


# ============================================================
# World drawing
# ============================================================
def draw_projectile(x, y, style, big=False):
    p = PROJECTILES.get(style, PROJECTILES[1])
    cx, cy = int(x + 7), int(y + 7)
    rad = 8 if big else 6
    if style == 1:
        pygame.draw.circle(screen, p["accent"], (cx, cy + 2), rad + 3)
        pygame.draw.circle(screen, p["main"], (cx, cy), rad)
        pygame.draw.polygon(screen, p["accent"], [(cx - 4, cy - rad), (cx, cy - rad - 5), (cx + 4, cy - rad)])
    elif style == 2:
        pygame.draw.circle(screen, p["main"], (cx, cy), rad)
        for a in range(0, 180, 45):
            rr = math.radians(a)
            dx, dy = int(math.cos(rr) * rad), int(math.sin(rr) * rad)
            pygame.draw.line(screen, p["accent"], (cx - dx, cy - dy), (cx + dx, cy + dy), 1)
    elif style == 3:
        pygame.draw.circle(screen, p["main"], (cx, cy), rad + 1)
        pygame.draw.circle(screen, PIX_CREAM, (cx - 2, cy - 2), 2)
    elif style == 4:
        pts = [(cx - 3, cy - rad - 3), (cx + 2, cy), (cx - 2, cy), (cx + 4, cy + rad + 3),
               (cx, cy + 2), (cx + 3, cy + 2)]
        pygame.draw.polygon(screen, p["accent"], pts)
    elif style == 5:
        pygame.draw.circle(screen, p["main"], (cx, cy), rad + 1)
        pygame.draw.polygon(screen, p["accent"], [(cx - 5, cy + 3), (cx, cy - 6), (cx + 5, cy + 3)])
    else:
        pygame.draw.circle(screen, p["main"], (cx, cy), rad)
        for a in range(0, 360, 60):
            rr = math.radians(a)
            pygame.draw.line(screen, p["accent"],
                             (cx + int(math.cos(rr) * (rad + 2)), cy + int(math.sin(rr) * (rad + 2))),
                             (cx + int(math.cos(rr) * (rad + 5)), cy + int(math.sin(rr) * (rad + 5))), 2)


def draw_boss(b):
    x, y = int(b["x"]), int(b["y"])
    ratio = clamp(b["hp"] / max(1, b["max_hp"]), 0.0, 1.0)
    bright = (pygame.time.get_ticks() // 250) % 2 == 0
    screen.blit(boss_surface(ratio < 0.3, bright), (x + 10, y))
    bw = 330
    bx = WIDTH // 2 - bw // 2
    pygame.draw.rect(screen, PIX_INK, (bx, 12, bw, 16))
    pygame.draw.rect(screen, PIX_RED if ratio < 0.3 else PIX_ORANGE, (bx + 2, 14, int((bw - 4) * ratio), 12))
    pygame.draw.rect(screen, PIX_CREAM, (bx, 12, bw, 16), 2)
    text("TRÙM MÀN %d • HP %d" % (G.W.level if G.W else 1, max(0, int(b["hp"]))), F_TINY, PIX_CREAM,
         WIDTH // 2, 32, "midtop")


def draw_powerup(pu):
    cfg = POWERUPS.get(pu["kind"], POWERUPS["HP"])
    x, y = int(pu["x"]), int(pu["y"])
    draw_wavy_rect(pygame.Rect(x, y, 30, 30), cfg["accent"], cfg["color"], 2, 1)
    text(cfg["label"], F_TINY, PIX_INK, x + 15, y + 15, "center")


def draw_hearts(x, y, hp):
    for i in range(MAX_HP):
        screen.blit(heart_surface(i < hp), (x + i * 24, y - 4))


def draw_world(w):
    update_thrusters()
    update_particles()
    for pu in w.powerups:
        draw_powerup(pu)
    for bl in w.bullets:
        draw_projectile(bl["x"], bl["y"], bl.get("style", 1), bool(bl.get("big")))
    for eb in w.ebullets:
        ex_, ey_ = int(eb["x"]) + 5, int(eb["y"]) + 10
        pygame.draw.polygon(screen, PIX_ORANGE, [(ex_, ey_ - 10), (ex_ + 6, ey_), (ex_, ey_ + 10), (ex_ - 6, ey_)])
        pygame.draw.rect(screen, PIX_CREAM, (ex_ - 2, ey_ - 4, 4, 8))
    for e in w.enemies:
        draw_enemy(e)
    if w.boss:
        draw_boss(w.boss)
    li = 1 if G.mode == "guest" else 0
    for i, p in enumerate(w.players):
        if not p.alive or not p.connected:
            continue
        if p.inv > 0 and (p.inv // 4) % 2 == 0:
            continue
        draw_ship(p.x, p.y, p.skin, upgrade=p.upgrade_flash > 0 or p.overdrive_frames > 0, shield=p.shield_frames > 0)
        if len(w.players) > 1:
            text(p.name[:10], F_TINY, PIX_MINT if i == li else PIX_GOLD, p.x + 27, p.y - 10, "midtop")

    draw_wavy_rect(pygame.Rect(10, 10, 208, 126), PIX_DIM, (20, 16, 32))
    text("SCORE", F_TINY, PIX_DIM, 22, 18)
    text("%06d" % w.score, F_LARGE, PIX_CREAM, 22, 31)
    text("COIN: %d" % P["coins"], F_SMALL, PIX_GOLD, 22, 70)
    text("HP", F_TINY, PIX_MINT, 22, 97)
    me = w.players[li]
    draw_hearts(56, 102, me.hp if me.alive else 0)

    draw_wavy_rect(pygame.Rect(WIDTH - 185, 10, 175, 100), PIX_DIM, (20, 16, 32))
    text("MÀN %d/%d" % (w.level, MAX_LEVELS), F_MED, PIX_MINT, WIDTH - 97, 25, "center")
    text("ĐẠN: %d TIA" % bullet_count_for_level(w.level), F_SMALL, PIX_GOLD, WIDTH - 97, 49, "center")
    text(DIFFS[G.difficulty]["name"], F_TINY, DIFFS[G.difficulty]["color"], WIDTH - 97, 73, "center")
    if len(w.players) > 1:
        text("CO-OP", F_TINY, PIX_PINK, WIDTH - 97, 90, "center")

    if len(w.players) > 1 and w.players[1 - li].connected:
        other = w.players[1 - li]
        draw_wavy_rect(pygame.Rect(10, 145, 200, 48), PIX_GOLD, (20, 16, 32))
        text(other.name[:12], F_TINY, PIX_GOLD, 20, 153)
        draw_hearts(56, 170, other.hp if other.alive else 0)

    if me.shield_frames > 0:
        text("BẢO VỆ %ds" % math.ceil(me.shield_frames / 60), F_TINY, PIX_BLUE, 222, HEIGHT - 43)
    elif me.overdrive_frames > 0:
        text("THĂNG CẤP %ds" % math.ceil(me.overdrive_frames / 60), F_TINY, PIX_GOLD, 222, HEIGHT - 43)
    else:
        text("ĐẠN: %s" % PROJECTILES[me.projectile_style]["name"], F_TINY, PROJECTILES[me.projectile_style]["accent"], 222, HEIGHT - 43)

    if not me.alive and w.state == "PLAYING":
        text("BẠN ĐÃ GỤC • CHỜ ĐỒNG ĐỘI", F_SMALL, PIX_RED, WIDTH // 2, HEIGHT // 2 - 20, "midtop")
    if G.mode == "guest" and not G.got_snapshot:
        text("ĐANG ĐỒNG BỘ...", F_MED, PIX_CREAM, WIDTH // 2, HEIGHT // 2, "midtop")
    if w.flash_timer > 0 and w.flash_message:
        draw_wavy_rect(pygame.Rect(110, 82, 380, 48), PIX_GOLD, (34, 24, 43))
        text(w.flash_message, F_MED, PIX_GOLD, WIDTH // 2, 106, "center")

    button(pygame.Rect(WIDTH - 82, HEIGHT - 52, 62, 36), "II", lambda: set_play_state("PAUSED"), border=PIX_GOLD, font=F_MED)

    text("WASD / ←↑↓→  •  SPACE/J", F_TINY, PIX_DIM, 12, HEIGHT - 24)
    # Hiện route + RTT ở góc dưới phải
    if G.net and G.route:
        rtt_txt = " %.0fms" % (G.net.rtt * 1000) if G.net.rtt is not None else ""
        text("%s%s" % (G.route, rtt_txt), F_TINY, PIX_MINT, WIDTH - 12, HEIGHT - 24, "topright")


def draw_pause():
    shade_s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    shade_s.fill((6, 4, 14, 160))
    screen.blit(shade_s, (0, 0))
    r = pygame.Rect(90, 225, WIDTH - 180, 220)
    draw_wavy_rect(r, PIX_GOLD, (28, 21, 39))
    text("TẠM DỪNG", F_LARGE, PIX_GOLD, WIDTH // 2, 252, "midtop")
    button(pygame.Rect(125, 330, 150, 44), "TIẾP TỤC", lambda: set_play_state("PLAYING"),
           base=(37, 104, 78), border=PIX_MINT, font=F_MED)
    button(pygame.Rect(325, 330, 150, 44), "MENU", to_menu_from_game,
           base=(104, 35, 40), border=PIX_RED, font=F_MED)


def to_menu_from_game():
    leave_match()
    set_state("MENU")


def set_play_state(s):
    G.state = s


def draw_end():
    shade_s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    shade_s.fill((6, 4, 14, 140))
    screen.blit(shade_s, (0, 0))
    win = G.state == "VICTORY"
    col = PIX_MINT if win else PIX_RED
    draw_wavy_rect(pygame.Rect(70, 180, WIDTH - 140, 340), col, (25, 19, 39), 3)
    text("PHÁ ĐẢO!" if win else "GAME OVER", F_LARGE, col, WIDTH // 2, 215, "midtop")
    text("50/50 MÀN" if win else "Bị hạ gục", F_MED, PIX_CREAM, WIDTH // 2, 262, "midtop")
    w = G.W
    score = w.score if w else 0
    text("Điểm: %d" % score, F_MED, PIX_CREAM, WIDTH // 2, 300, "midtop")
    text("Kỷ lục: %d" % P["hs"], F_MED, PIX_GOLD, WIDTH // 2, 331, "midtop")
    text("Xu: %d" % P["coins"], F_SMALL, PIX_GOLD, WIDTH // 2, 364, "midtop")
    coop = bool(w and len(w.players) > 1)
    if not coop and not win:
        button(pygame.Rect(110, 425, 180, 48), "CHƠI LẠI", start_solo, base=(37, 104, 78), border=PIX_MINT, font=F_MED)
        button(pygame.Rect(310, 425, 180, 48), "MENU", to_menu_from_game, border=PIX_BLUE, font=F_MED)
    else:
        button(pygame.Rect(210, 425, 180, 48), "MENU", to_menu_from_game, border=PIX_BLUE, font=F_MED)


# ============================================================
# Overlays + input
# ============================================================
def draw_overlays():
    if G.invite and time.time() - G.invite["t"] > 30:
        G.invite = None
    if G.invite and G.state not in ("PLAYING", "PAUSED", "SPLASH", "LOGIN"):
        shade_s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade_s.fill((0, 0, 0, 165))
        screen.blit(shade_s, (0, 0))
        r = pygame.Rect(65, 250, WIDTH - 130, 180)
        draw_wavy_rect(r, PIX_PURPLE, (28, 21, 40), 3)
        text("LỜI MỜI CHƠI ĐÔI", F_MED, PIX_PURPLE, WIDTH // 2, 270, "midtop")
        text("%s mời bạn!" % G.invite["from"], F_MED, PIX_CREAM, WIDTH // 2, 309, "midtop")
        button(pygame.Rect(r.x + 35, 356, 150, 42), "ĐỒNG Ý", accept_invite, base=(37, 104, 78), border=PIX_MINT, font=F_MED)
        button(pygame.Rect(r.right - 185, 356, 150, 42), "TỪ CHỐI", decline_invite,
               base=(104, 35, 40), border=PIX_RED, font=F_MED)
    if G.toast_msg and time.time() < G.toast_until:
        s = F_SMALL.render(G.toast_msg, False, PIX_CREAM)
        r = pygame.Rect(0, 0, s.get_width() + 26, 30)
        r.midtop = (WIDTH // 2, 6)
        draw_wavy_rect(r, G.toast_color, (22, 17, 32), 2, 1)
        screen.blit(s, s.get_rect(center=r.center))


def handle_text_key(ev):
    key = G.focus
    if key not in fields:
        return False
    if ev.key in (pygame.K_ESCAPE, pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
        return False
    if ev.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
        fields[key] = fields[key][:-1]
        return True
    if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
        if G.state == "LOGIN":
            submit_auth()
        elif G.state == "FRIENDS":
            add_friend()
        elif G.state == "CHAT":
            send_chat()
        return True
    if ev.key == pygame.K_TAB and G.state == "LOGIN":
        order = ["user", "pass"]
        try:
            G.focus = order[(order.index(key) + 1) % 2]
        except ValueError:
            G.focus = order[0]
        return True
    return True


def handle_event(ev):
    if ev.type == pygame.QUIT:
        return False
    if G.state == "SPLASH":
        if ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            G.splash = 90
        return True
    if ev.type == pygame.TEXTINPUT:
        key = G.focus
        if key in fields:
            ch = "".join(c for c in (ev.text or "") if c.isprintable())
            if key in ("user", "friend"):
                ch = "".join(c for c in ch if c.isascii() and (c.isalnum() or c == "_"))
            room = FIELD_MAX[key] - len(fields[key])
            if room > 0:
                fields[key] += ch[:room]
        return True
    if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
        for rect, fn in reversed(prev_hits):
            if rect.collidepoint(ev.pos):
                try:
                    fn()
                except Exception as ex:
                    toast("Lỗi thao tác: %s" % ex, False)
                break
    elif ev.type == pygame.MOUSEWHEEL:
        if G.state in ("FRIENDS", "BOARD"):
            G.scroll -= ev.y * 30
        elif G.state == "CHAT":
            G.chat_scroll = getattr(G, "chat_scroll", 0) + ev.y * 30
    elif ev.type == pygame.KEYDOWN:
        if G.state == "CHAT" and G.focus is None:
            if ev.key == pygame.K_UP:
                G.chat_scroll = getattr(G, "chat_scroll", 0) + 35
                return True
            if ev.key == pygame.K_DOWN:
                G.chat_scroll = getattr(G, "chat_scroll", 0) - 35
                return True
        if handle_text_key(ev):
            return True
        if G.state == "PLAYING" and ev.key in (pygame.K_ESCAPE, pygame.K_p):
            set_play_state("PAUSED")
        elif G.state == "PAUSED" and ev.key in (pygame.K_ESCAPE, pygame.K_p, pygame.K_SPACE):
            set_play_state("PLAYING")
        elif G.state == "PLAYING" and ev.key == pygame.K_F2:
            to_menu_from_game()
        elif ev.key == pygame.K_ESCAPE and G.state in ("DIFF", "SHOP_SKIN", "SHOP_PROJECTILE", "PROFILE", "FRIENDS", "BOARD", "CHAT"):
            set_state("MENU")
    return True


# ============================================================
# Main loop
# ============================================================
def frame():
    global hits, prev_hits
    prev_hits, hits = hits, []
    G.mouse = pygame.mouse.get_pos()
    G.tick += 1

    pump_net()
    for ev in pygame.event.get():
        if not handle_event(ev):
            leave_match()
            if G.user:
                send_save()
            return False

    if G.conn_lost and G.state not in ("LOGIN", "SPLASH"):
        if not (G.mode == "solo" and G.state in ("PLAYING", "PAUSED", "GAME_OVER", "VICTORY")):
            go_login("Mất kết nối. Đăng nhập lại.")

    now = time.time()
    if G.user and G.net and not G.net.closed:
        if now - G.last_ping > 25:
            G.last_ping = now
            net_send({"t": "ping"})
        if G.save_dirty and now - G.last_save > 3:
            send_save()
        if G.state in ("FRIENDS", "BOARD", "CHAT") and now - G.last_refresh > 5:
            refresh_social()

    if G.state == "PLAYING":
        update_play()

    draw_stars()
    if G.state == "SPLASH":
        draw_splash()
    elif G.state == "LOGIN":
        update_particles()
        draw_login()
    elif G.state == "MENU":
        update_particles()
        draw_menu()
    elif G.state == "DIFF":
        update_particles()
        draw_diff()
    elif G.state == "SHOP_PROJECTILE":
        update_particles()
        draw_shop_projectile()
    elif G.state == "SHOP_SKIN":
        update_particles()
        draw_shop_skin()
    elif G.state == "PROFILE":
        update_particles()
        draw_profile()
    elif G.state == "FRIENDS":
        update_particles()
        draw_friends()
    elif G.state == "BOARD":
        update_particles()
        draw_board()
    elif G.state == "CHAT":
        update_particles()
        draw_chat()
    elif G.state in ("PLAYING", "PAUSED", "GAME_OVER", "VICTORY") and G.W is not None:
        draw_world(G.W)
        if G.state == "PAUSED":
            draw_pause()
        elif G.state in ("GAME_OVER", "VICTORY"):
            draw_end()

    draw_overlays()
    if not hasattr(frame, "scanlines"):
        frame.scanlines = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for yy in range(0, HEIGHT, 4):
            pygame.draw.line(frame.scanlines, (0, 0, 0, 20), (0, yy), (WIDTH, yy))
    screen.blit(frame.scanlines, (0, 0))
    pygame.display.flip()
    clock.tick(FPS)
    return True


def main():
    load_config()
    while frame():
        pass
    if G.net:
        G.net.close()
    pygame.quit()


if __name__ == "__main__":
    main()
