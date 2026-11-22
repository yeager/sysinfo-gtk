# SysInfo GTK

SysInfo GTK is a GTK 4 and libadwaita desktop application for viewing hardware and operating system details on Linux. It groups information into navigable sections and can export a plain-text system report.

## Features

- System summary, kernel, architecture, uptime, and logged-in users
- Processor model, thread and core counts, supported CPU features, and load average
- Memory and swap use, with optional memory module details when `dmidecode` can read them without elevation
- Storage, mounted filesystems, graphics, display session, and network interfaces
- PCI and USB devices, sensors, battery, and loaded kernel modules
- CPU, memory-copy, and disk I/O benchmarks
- Copyable rows and sections, report export, and Swedish translations

Some hardware details depend on optional system utilities and permissions. Missing tools or unavailable hardware information are shown as unavailable; the application does not request administrator access.

## Requirements

- Linux with Python 3.10 or newer
- GTK 4 and libadwaita 1
- PyGObject for Python

Optional collectors use tools such as `dmidecode`, `df`, `lsblk`, `lspci`, `lsusb`, `sensors`, `ip`, `ifconfig`, `xrandr`, `glxinfo`, and `vulkaninfo`. The application will skip information when a utility is missing.

## Install

### Debian and Ubuntu

Add the Yeager APT repository and install the package:

```sh
echo "deb https://yeager.github.io/debian-repo stable main" | sudo tee /etc/apt/sources.list.d/yeager-l10n.list
sudo apt update
sudo apt install sysinfo-gtk
```

### Fedora and compatible DNF systems

```sh
sudo dnf config-manager --add-repo https://yeager.github.io/rpm-repo/yeager-l10n.repo
sudo dnf install sysinfo-gtk
```

### From a release package

Download the latest `.deb` or `.rpm` from [GitHub Releases](https://github.com/yeager/sysinfo-gtk/releases/latest), then install it using your distribution's package manager. The packages declare their GTK, libadwaita, and Python bindings as dependencies.

## Run from source

Install the GTK 4 and libadwaita development/runtime packages provided by your distribution, then install PyGObject and this project:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
sysinfo-gtk
```

On distributions where PyGObject is only available as a system package, install the distribution package (commonly named `python3-gi`) and use the system Python instead of a virtual environment.

## Translation

English is the source language. Swedish translations are maintained in `po/sv.po`. The project is managed on [Transifex](https://app.transifex.com/danielnylander/sysinfo-gtk/).

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).

## Links

- [Source code](https://github.com/yeager/sysinfo-gtk)
- [Report an issue](https://github.com/yeager/sysinfo-gtk/issues)
- [Author: Daniel Nylander](mailto:daniel@danielnylander.se)
