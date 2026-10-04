# Tienkj Game

A Python/Pygame multiplayer space-shooter game developed as an independent open-source project.

## About

**Tienkj Game** is a 2D space-shooter game written in Python using Pygame.

The game combines arcade-style shooting gameplay with online features such as account authentication, friends, leaderboards, global chat, private messaging, and cooperative gameplay.

The project is developed and maintained independently and is released as open-source software.

## Features

* Space-shooter gameplay
* Multiple difficulty levels
* Player progression and scoring
* Unlockable spaceship skins
* Projectile upgrades
* Online account authentication
* Friends system
* Leaderboards
* Global chat
* Private messaging
* Cooperative gameplay
* IPv4/IPv6 network connectivity

## Requirements

### Running from source

* Windows, Linux, or another platform supported by Python and Pygame
* Python 3.11 or newer
* Pygame

Install the dependency:

```bash
python -m pip install pygame
```

Run the game:

```bash
python game.py
```

## Building the Windows executable

The project uses PyInstaller to create a standalone Windows executable.

Install the build dependencies:

```bash
python -m pip install pygame pyinstaller
```

Build:

```bash
pyinstaller --noconfirm --clean --onefile --windowed --name TienkjGame game.py
```

The resulting executable will be located at:

```text
dist/TienkjGame.exe
```

Official Windows builds are produced automatically using GitHub Actions.

## Network Features

Tienkj Game contains online functionality.

The current client connects to the project's configured game server using IPv4 and/or IPv6. Online functionality may include:

* Account authentication
* Player profiles
* Friends
* Leaderboards
* Global chat
* Private chat
* Cooperative rooms

The game may transmit information entered or generated while using these online features, such as account credentials, usernames, chat messages, scores, friend information, and connection-related information.

Do not use an account or enter information that you do not want to transmit to the project's server.

## Privacy

This project may process user-provided information required for online gameplay.

If you use the online features, information may be transmitted to the project's game server for authentication, gameplay, social features, chat, and leaderboard functionality.

A separate privacy policy should be provided before distributing releases that collect or process user data.

## Code Signing

Official Windows releases of Tienkj Game are intended to be code-signed through the **SignPath Foundation** program.

Code signing is used to provide release authenticity and integrity.

The SignPath Foundation certificate is issued in SignPath Foundation's name in accordance with its program requirements.

## Open Source

The source code is publicly available on GitHub:

https://github.com/Tienkj/tienkjgame

Contributions, bug reports, and suggestions are welcome.

## License

This project is licensed under the MIT License.

See [LICENSE](LICENSE) for details.

## Disclaimer

This is an independent open-source project.

The game requires an internet connection for its online features. Server availability is not guaranteed.

The developers are not responsible for network outages, third-party infrastructure failures, or loss of online game data.

## Project Status

The project is actively maintained as an independent open-source game project.

## Author

**Tienkj**

GitHub:

https://github.com/Tienkj
