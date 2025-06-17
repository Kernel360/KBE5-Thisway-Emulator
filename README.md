# Thisway Emulator

A lightweight emulator for generating vehicle GPS data and sending it to a backend server.

## Overview

This emulator generates realistic GPS data for vehicles and sends it to a backend server. It can simulate multiple vehicles simultaneously, each with its own Mobile Device Number (MDN).

## Installation

1. Clone the repository
2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

The emulator can be used in two modes: command-line mode and interactive mode.

### Command-line Mode

Start an emulator for a specific MDN:

```bash
python main.py start <mdn>
```

Stop an emulator:

```bash
python main.py stop <mdn>
```

Generate GPS log data:

```bash
python main.py generate <mdn> [--realtime] [--no-store]
```

Get pending logs:

```bash
python main.py pending <mdn>
```

List all active emulators:

```bash
python main.py list
```

### Interactive Mode

Run the emulator in interactive mode:

```bash
python main.py interactive
```

In interactive mode, you can use the following commands:

- `start <mdn>` - Start an emulator for the given MDN
- `stop <mdn>` - Stop the emulator for the given MDN
- `generate <mdn> [realtime] [store]` - Generate GPS log data
- `pending <mdn>` - Get pending logs for the given MDN
- `list` - List all active emulators
- `help` - Show help message
- `exit` or `quit` - Exit the program

## Configuration

The emulator uses the following configuration settings from `config.py`:

- `DEFAULT_LATITUDE` and `DEFAULT_LONGITUDE` - Default location for new emulators
- `API_HOST` and `API_PORT` - Host and port for the backend server

You can modify these settings in `config.py` or set them using environment variables.

## Example

```bash
# Start the emulator in interactive mode
python main.py interactive

# In interactive mode
> start 1234567890
Started emulator for MDN: 1234567890

> generate 1234567890 realtime
Started realtime data collection for MDN 1234567890. Logs will be generated every 60 seconds.

> list
Active emulators: 1
MDN: 1234567890, Status: Active, Position: (37.5665, 126.9780)

> stop 1234567890
Stopped emulator for MDN: 1234567890

> exit
Exiting...
```

## Architecture

The emulator consists of several components:

- `EmulatorCLI` - Command-line interface for the emulator
- `EmulatorManager` - Manages emulator instances
- `GpsLogGenerator` - Generates GPS log data
- `LogStorageManager` - Stores and sends logs to the backend server

## License

This project is licensed under the MIT License - see the LICENSE file for details.