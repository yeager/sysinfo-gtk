"""SysInfo GTK — GTK4/Adwaita system information and benchmark tool."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, Gio, GLib, Pango

import gettext
import locale
import os
import sys
import json
import platform
import subprocess
import threading
import re
import time
import glob
import struct

LOCALE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "po")
if not os.path.isdir(LOCALE_DIR):
    LOCALE_DIR = "/usr/share/locale"
locale.bindtextdomain("sysinfo-gtk", LOCALE_DIR)
gettext.bindtextdomain("sysinfo-gtk", LOCALE_DIR)
gettext.textdomain("sysinfo-gtk")
_ = gettext.gettext

APP_ID = "se.danielnylander.sysinfo-gtk"
SETTINGS_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "sysinfo-gtk"
)
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")


def _load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    return {"welcome_shown": False}


def _save_settings(s):
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)


# ── Data collectors ──────────────────────────────────────────

def _cmd(args, timeout=5):
    """Run command, return stdout or empty string."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except:
        return ""


def _read_file(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except:
        return ""


def collect_summary():
    """System summary."""
    info = {}
    info[_("Hostname")] = platform.node()
    info[_("OS")] = _read_file("/etc/os-release").split("\n")[0].replace("PRETTY_NAME=", "").strip('"') or platform.platform()
    info[_("Kernel")] = platform.release()
    info[_("Architecture")] = platform.machine()
    info[_("Desktop")] = os.environ.get("XDG_CURRENT_DESKTOP", os.environ.get("DESKTOP_SESSION", _("Unknown")))

    # Uptime
    uptime_s = _read_file("/proc/uptime").split()[0] if os.path.exists("/proc/uptime") else ""
    if uptime_s:
        secs = int(float(uptime_s))
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        mins = rem // 60
        info[_("Uptime")] = f"{days}d {hours}h {mins}m"

    # Users
    who = _cmd(["who"])
    if who:
        users = set(l.split()[0] for l in who.splitlines() if l.strip())
        info[_("Logged in users")] = ", ".join(sorted(users))

    return _("Summary"), "computer-symbolic", info


def collect_cpu():
    """CPU information."""
    info = {}
    if os.path.exists("/proc/cpuinfo"):
        cpuinfo = _read_file("/proc/cpuinfo")
        models = set()
        cores = 0
        for line in cpuinfo.splitlines():
            if line.startswith("model name"):
                models.add(line.split(":", 1)[1].strip())
            if line.startswith("processor"):
                cores += 1
        if models:
            info[_("Model")] = ", ".join(models)
        info[_("Threads")] = str(cores)

        # Physical cores
        physical = set()
        for line in cpuinfo.splitlines():
            if line.startswith("core id"):
                physical.add(line.split(":", 1)[1].strip())
        if physical:
            info[_("Physical cores")] = str(len(physical))

        # MHz
        for line in cpuinfo.splitlines():
            if line.startswith("cpu MHz"):
                mhz = float(line.split(":", 1)[1].strip())
                info[_("Current frequency")] = f"{mhz:.0f} MHz"
                break

        # Cache
        for line in cpuinfo.splitlines():
            if line.startswith("cache size"):
                info[_("Cache")] = line.split(":", 1)[1].strip()
                break

        # Flags (selected)
        for line in cpuinfo.splitlines():
            if line.startswith("flags"):
                flags = line.split(":", 1)[1].strip().split()
                interesting = [f for f in flags if f in (
                    "sse4_2", "avx", "avx2", "avx512f", "aes", "ssse3",
                    "ht", "vmx", "svm", "nx", "lm", "pae"
                )]
                if interesting:
                    info[_("Features")] = ", ".join(sorted(interesting))
                break
    else:
        # macOS / other
        info[_("Model")] = platform.processor() or _("Unknown")

    # Load average
    if os.path.exists("/proc/loadavg"):
        load = _read_file("/proc/loadavg").split()[:3]
        info[_("Load average")] = " / ".join(load)

    return _("Processor"), "processor-symbolic", info


def collect_memory():
    """Memory information."""
    info = {}
    if os.path.exists("/proc/meminfo"):
        meminfo = _read_file("/proc/meminfo")
        vals = {}
        for line in meminfo.splitlines():
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip()
                val = parts[1].strip().split()[0]
                vals[key] = int(val)

        total = vals.get("MemTotal", 0)
        avail = vals.get("MemAvailable", vals.get("MemFree", 0))
        used = total - avail
        swap_total = vals.get("SwapTotal", 0)
        swap_free = vals.get("SwapFree", 0)

        info[_("Total")] = f"{total // 1024} MB ({total // 1048576:.1f} GB)"
        info[_("Available")] = f"{avail // 1024} MB"
        info[_("Used")] = f"{used // 1024} MB ({used * 100 // total}%)" if total else "?"
        if swap_total:
            info[_("Swap total")] = f"{swap_total // 1024} MB"
            info[_("Swap used")] = f"{(swap_total - swap_free) // 1024} MB"

        # Memory type from DMI
        dmi_mem = _cmd(["sudo", "dmidecode", "-t", "memory"], timeout=2)
        if not dmi_mem:
            dmi_mem = _cmd(["dmidecode", "-t", "memory"], timeout=2)
        if dmi_mem:
            for line in dmi_mem.splitlines():
                line = line.strip()
                if line.startswith("Type:") and "Unknown" not in line:
                    info[_("Type")] = line.split(":", 1)[1].strip()
                    break
                if line.startswith("Speed:") and "Unknown" not in line:
                    info[_("Speed")] = line.split(":", 1)[1].strip()

    return _("Memory"), "memory-symbolic", info


def collect_storage():
    """Storage/disk information."""
    info = {}
    df = _cmd(["df", "-h", "--output=source,fstype,size,used,avail,pcent,target"])
    if df:
        for line in df.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 7 and not parts[0].startswith("tmpfs"):
                mount = parts[6]
                info[f"{mount}"] = f"{parts[0]} ({parts[1]}) — {parts[4]} free / {parts[2]} ({parts[5]} used)"

    # Block devices
    lsblk = _cmd(["lsblk", "-d", "-o", "NAME,SIZE,MODEL,ROTA,TYPE", "--noheadings"])
    if lsblk:
        info[""] = ""  # separator
        info[_("Block devices")] = ""
        for line in lsblk.splitlines():
            parts = line.split(None, 4)
            if len(parts) >= 3 and parts[-1] == "disk":
                name = parts[0]
                size = parts[1]
                model = parts[2] if len(parts) > 2 else ""
                rota = parts[3] if len(parts) > 3 else "1"
                disk_type = "HDD" if rota == "1" else "SSD"
                info[f"/dev/{name}"] = f"{size} {model} ({disk_type})"

    return _("Storage"), "drive-harddisk-symbolic", info


def collect_gpu():
    """GPU information."""
    info = {}
    lspci = _cmd(["lspci"])
    if lspci:
        for line in lspci.splitlines():
            if "VGA" in line or "3D" in line or "Display" in line:
                gpu_name = line.split(":", 2)[-1].strip() if ":" in line else line
                info[_("GPU")] = gpu_name

    # OpenGL
    glx = _cmd(["glxinfo"])
    if glx:
        for line in glx.splitlines():
            if "OpenGL renderer" in line:
                info[_("OpenGL renderer")] = line.split(":", 1)[1].strip()
            if "OpenGL version" in line:
                info[_("OpenGL version")] = line.split(":", 1)[1].strip()
                break

    # Vulkan
    vulkan = _cmd(["vulkaninfo", "--summary"])
    if vulkan:
        for line in vulkan.splitlines():
            if "deviceName" in line:
                info[_("Vulkan device")] = line.split("=", 1)[1].strip()
            if "apiVersion" in line and "=" in line:
                info[_("Vulkan API")] = line.split("=", 1)[1].strip()
                break

    if not info:
        info[_("GPU")] = _("No GPU detected (lspci not available?)")

    return _("Graphics"), "video-display-symbolic", info


def collect_network():
    """Network interfaces."""
    info = {}
    ip_out = _cmd(["ip", "-brief", "addr"])
    if ip_out:
        for line in ip_out.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                iface = parts[0]
                state = parts[1]
                addrs = " ".join(parts[2:])
                info[iface] = f"{state} — {addrs}"
            elif len(parts) == 2:
                info[parts[0]] = parts[1]
    else:
        # Fallback
        ifconfig = _cmd(["ifconfig"])
        if ifconfig:
            info[_("Network")] = ifconfig[:500]

    # DNS
    resolv = _read_file("/etc/resolv.conf")
    dns = [l.split()[1] for l in resolv.splitlines() if l.startswith("nameserver")]
    if dns:
        info[_("DNS servers")] = ", ".join(dns)

    return _("Network"), "network-wired-symbolic", info


def collect_pci():
    """PCI devices."""
    info = {}
    lspci = _cmd(["lspci", "-mm"])
    if lspci:
        for line in lspci.splitlines():
            # Parse mm format
            parts = line.split('"')
            if len(parts) >= 6:
                slot = parts[0].strip()
                cls = parts[1]
                vendor = parts[3]
                device = parts[5]
                info[slot] = f"{cls}: {vendor} {device}"
            else:
                info[line[:8]] = line[8:].strip()
    else:
        info[_("PCI")] = _("lspci not available")
    return _("PCI Devices"), "expansion-card-symbolic", info


def collect_usb():
    """USB devices."""
    info = {}
    lsusb = _cmd(["lsusb"])
    if lsusb:
        for line in lsusb.splitlines():
            m = re.match(r'Bus (\d+) Device (\d+): ID (\S+) (.*)', line)
            if m:
                info[f"Bus {m.group(1)} Dev {m.group(2)}"] = f"{m.group(3)} {m.group(4)}"
            else:
                info[line[:20]] = line[20:]
    else:
        info[_("USB")] = _("lsusb not available")
    return _("USB Devices"), "drive-removable-media-symbolic", info


def collect_sensors():
    """Temperature and fan sensors."""
    info = {}
    sensors = _cmd(["sensors"])
    if sensors:
        current_chip = ""
        for line in sensors.splitlines():
            if not line.startswith(" ") and line.strip() and ":" not in line:
                current_chip = line.strip()
            elif ":" in line:
                name, val = line.split(":", 1)
                name = name.strip()
                val = val.strip()
                if current_chip:
                    info[f"{current_chip} / {name}"] = val
                else:
                    info[name] = val
    else:
        # Try hwmon directly
        for hwmon in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            chip_name = _read_file(os.path.join(hwmon, "name"))
            for temp_file in sorted(glob.glob(os.path.join(hwmon, "temp*_input"))):
                try:
                    temp = int(_read_file(temp_file)) / 1000
                    label_file = temp_file.replace("_input", "_label")
                    label = _read_file(label_file) or os.path.basename(temp_file)
                    info[f"{chip_name} / {label}"] = f"{temp:.1f} °C"
                except:
                    pass

    if not info:
        info[_("Sensors")] = _("No sensor data available")
    return _("Sensors"), "sensors-temperature-symbolic", info


def collect_battery():
    """Battery information."""
    info = {}
    bat_path = "/sys/class/power_supply"
    if os.path.isdir(bat_path):
        for bat in os.listdir(bat_path):
            bat_type = _read_file(os.path.join(bat_path, bat, "type"))
            if bat_type == "Battery":
                status = _read_file(os.path.join(bat_path, bat, "status"))
                capacity = _read_file(os.path.join(bat_path, bat, "capacity"))
                energy_full = _read_file(os.path.join(bat_path, bat, "energy_full"))
                energy_design = _read_file(os.path.join(bat_path, bat, "energy_full_design"))
                tech = _read_file(os.path.join(bat_path, bat, "technology"))

                info[f"{bat} — " + _("Status")] = status or _("Unknown")
                if capacity:
                    info[f"{bat} — " + _("Capacity")] = f"{capacity}%"
                if tech:
                    info[f"{bat} — " + _("Technology")] = tech
                if energy_full and energy_design:
                    health = int(energy_full) * 100 // int(energy_design)
                    info[f"{bat} — " + _("Health")] = f"{health}%"

    if not info:
        info[_("Battery")] = _("No battery detected")
    return _("Battery"), "battery-symbolic", info


def collect_kernel_modules():
    """Loaded kernel modules."""
    info = {}
    lsmod = _cmd(["lsmod"])
    if lsmod:
        lines = lsmod.splitlines()[1:]  # skip header
        for line in sorted(lines):
            parts = line.split()
            if parts:
                mod = parts[0]
                size = parts[1] if len(parts) > 1 else ""
                used = parts[2] if len(parts) > 2 else ""
                info[mod] = f"{_('Size')}: {size}  {_('Used by')}: {used}"
    return _("Kernel Modules"), "application-x-firmware-symbolic", info


def collect_filesystems():
    """Mounted filesystems."""
    info = {}
    df = _cmd(["df", "-hT"])
    if df:
        lines = df.splitlines()
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 7 and not parts[0].startswith("tmpfs") and not parts[0].startswith("devtmpfs"):
                info[parts[6]] = f"{parts[0]} ({parts[1]}) — {parts[4]} avail / {parts[2]} total"
    return _("Filesystems"), "drive-multidisk-symbolic", info


def collect_display():
    """Display/monitor information."""
    info = {}
    xrandr = _cmd(["xrandr", "--current"])
    if xrandr:
        for line in xrandr.splitlines():
            if " connected" in line:
                info[line.split()[0]] = line.split(" connected", 1)[1].strip()
    wayland = os.environ.get("WAYLAND_DISPLAY", "")
    if wayland:
        info[_("Session")] = f"Wayland ({wayland})"
    elif os.environ.get("DISPLAY"):
        info[_("Session")] = f"X11 ({os.environ['DISPLAY']})"

    return _("Display"), "video-display-symbolic", info


def collect_environment():
    """Environment variables."""
    info = {}
    for key in sorted(os.environ):
        if key.startswith(("_", "LS_COLORS")):
            continue
        info[key] = os.environ[key][:200]
    return _("Environment"), "preferences-other-symbolic", info


# ── Benchmark ────────────────────────────────────────────────

def run_benchmark_cpu():
    """Simple CPU benchmark — prime number calculation."""
    import math
    start = time.monotonic()
    count = 0
    for n in range(2, 100000):
        is_prime = True
        for i in range(2, int(math.sqrt(n)) + 1):
            if n % i == 0:
                is_prime = False
                break
        if is_prime:
            count += 1
    elapsed = time.monotonic() - start
    return {
        _("Test"): _("Prime numbers up to 100,000"),
        _("Primes found"): str(count),
        _("Time"): f"{elapsed:.3f} s",
        _("Score"): f"{int(10000 / elapsed)}",
    }


def run_benchmark_memory():
    """Memory bandwidth benchmark."""
    size = 10 * 1024 * 1024  # 10 MB
    data = bytearray(size)

    start = time.monotonic()
    for i in range(10):
        _ = bytes(data)
    elapsed = time.monotonic() - start

    bandwidth = (size * 10) / elapsed / 1024 / 1024
    return {
        gettext.gettext("Test"): gettext.gettext("Memory copy 10×10 MB"),
        gettext.gettext("Time"): f"{elapsed:.3f} s",
        gettext.gettext("Bandwidth"): f"{bandwidth:.0f} MB/s",
    }


def run_benchmark_disk():
    """Disk I/O benchmark."""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False)
    data = os.urandom(1024 * 1024)  # 1 MB

    # Write
    start = time.monotonic()
    for i in range(50):
        tmp.write(data)
    tmp.flush()
    os.fsync(tmp.fileno())
    write_time = time.monotonic() - start

    # Read
    tmp.seek(0)
    start = time.monotonic()
    while tmp.read(1024 * 1024):
        pass
    read_time = time.monotonic() - start

    tmp.close()
    os.unlink(tmp.name)

    return {
        gettext.gettext("Test"): gettext.gettext("Disk I/O 50 MB"),
        gettext.gettext("Write"): f"{50 / write_time:.0f} MB/s ({write_time:.3f} s)",
        gettext.gettext("Read"): f"{50 / read_time:.0f} MB/s ({read_time:.3f} s)",
    }


# ── All sections ─────────────────────────────────────────────

SECTIONS = [
    collect_summary,
    collect_cpu,
    collect_memory,
    collect_storage,
    collect_gpu,
    collect_display,
    collect_network,
    collect_sensors,
    collect_battery,
    collect_pci,
    collect_usb,
    collect_filesystems,
    collect_kernel_modules,
    collect_environment,
]


# ── Main Window ──────────────────────────────────────────────

class SysInfoWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=_("System Information"), default_width=1100, default_height=750)
        self.settings = _load_settings()
        self._sections_data = {}

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header
        headerbar = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title=_("System Information"), subtitle=platform.node())
        headerbar.set_title_widget(title_widget)
        self._title_widget = title_widget

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_("Refresh all"))
        refresh_btn.connect("clicked", self._on_refresh)
        headerbar.pack_start(refresh_btn)

        copy_btn = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=_("Copy current section"))
        copy_btn.connect("clicked", self._on_copy_section)
        headerbar.pack_start(copy_btn)

        export_btn = Gtk.Button(icon_name="document-save-symbolic", tooltip_text=_("Export full report"))
        export_btn.connect("clicked", self._on_export)
        headerbar.pack_end(export_btn)

        # Menu
        menu = Gio.Menu()
        bench_menu = Gio.Menu()
        bench_menu.append(_("CPU Benchmark"), "app.bench-cpu")
        bench_menu.append(_("Memory Benchmark"), "app.bench-mem")
        bench_menu.append(_("Disk Benchmark"), "app.bench-disk")
        menu.append_section(_("Benchmarks"), bench_menu)
        menu.append(_("Copy Debug Info"), "app.copy-debug")
        menu.append(_("Keyboard Shortcuts"), "app.shortcuts")
        menu.append(_("About System Information"), "app.about")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        headerbar.pack_end(menu_btn)

        main_box.append(headerbar)

        # Content: sidebar + detail
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)

        # Left: category list
        left_scroll = Gtk.ScrolledWindow()
        left_scroll.set_size_request(220, -1)
        self._cat_list = Gtk.ListBox()
        self._cat_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._cat_list.add_css_class("navigation-sidebar")
        self._cat_list.connect("row-selected", self._on_cat_selected)
        left_scroll.set_child(self._cat_list)
        paned.set_start_child(left_scroll)

        # Right: detail list
        right_scroll = Gtk.ScrolledWindow()
        right_scroll.set_vexpand(True)
        self._detail_list = Gtk.ListBox()
        self._detail_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._detail_list.add_css_class("boxed-list")
        self._detail_list.set_margin_start(12)
        self._detail_list.set_margin_end(12)
        self._detail_list.set_margin_top(8)
        self._detail_list.set_margin_bottom(8)
        right_scroll.set_child(self._detail_list)
        paned.set_end_child(right_scroll)
        paned.set_position(220)

        main_box.append(paned)

        # Status
        self._status = Gtk.Label(label=_("Loading..."), xalign=0)
        self._status.set_margin_start(12)
        self._status.set_margin_end(12)
        self._status.set_margin_top(4)
        self._status.set_margin_bottom(4)
        self._status.add_css_class("dim-label")
        main_box.append(self._status)

        self.set_content(main_box)

        # Welcome
        if not self.settings.get("welcome_shown"):
            GLib.idle_add(self._show_welcome)

        # Load data
        self._populate_categories()
        threading.Thread(target=self._load_all, daemon=True).start()

    def _show_welcome(self):
        dialog = Adw.Dialog()
        dialog.set_title(_("Welcome"))
        dialog.set_content_width(420)
        dialog.set_content_height(480)

        page = Adw.StatusPage()
        page.set_icon_name("computer-symbolic")
        page.set_title(_("Welcome to System Information"))
        page.set_description(_(
            "Detailed hardware and software information.\\n\\n"
            "✓ CPU, memory, storage, GPU details\\n"
            "✓ PCI and USB device listing\\n"
            "✓ Temperature and fan sensors\\n"
            "✓ Network interfaces\\n"
            "✓ CPU, memory, and disk benchmarks\\n"
            "✓ Export full system report"
        ))

        btn = Gtk.Button(label=_("Get Started"))
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(12)
        btn.connect("clicked", self._on_welcome_close, dialog)
        page.set_child(btn)

        box = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        hb.set_show_title(False)
        box.add_top_bar(hb)
        box.set_content(page)
        dialog.set_child(box)
        dialog.present(self)

    def _on_welcome_close(self, btn, dialog):
        self.settings["welcome_shown"] = True
        _save_settings(self.settings)
        dialog.close()

    def _populate_categories(self):
        self._cat_rows = []
        for collector in SECTIONS:
            # Get name without running the full collector
            names = {
                collect_summary: (_("Summary"), "computer-symbolic"),
                collect_cpu: (_("Processor"), "processor-symbolic"),
                collect_memory: (_("Memory"), "memory-symbolic"),
                collect_storage: (_("Storage"), "drive-harddisk-symbolic"),
                collect_gpu: (_("Graphics"), "video-display-symbolic"),
                collect_display: (_("Display"), "video-display-symbolic"),
                collect_network: (_("Network"), "network-wired-symbolic"),
                collect_sensors: (_("Sensors"), "sensors-temperature-symbolic"),
                collect_battery: (_("Battery"), "battery-symbolic"),
                collect_pci: (_("PCI Devices"), "expansion-card-symbolic"),
                collect_usb: (_("USB Devices"), "drive-removable-media-symbolic"),
                collect_filesystems: (_("Filesystems"), "drive-multidisk-symbolic"),
                collect_kernel_modules: (_("Kernel Modules"), "application-x-firmware-symbolic"),
                collect_environment: (_("Environment"), "preferences-other-symbolic"),
            }
            name, icon = names.get(collector, (_("Unknown"), "dialog-question-symbolic"))

            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.set_margin_start(8)
            box.set_margin_end(8)
            box.set_margin_top(6)
            box.set_margin_bottom(6)
            img = Gtk.Image.new_from_icon_name(icon)
            img.set_pixel_size(20)
            box.append(img)
            lbl = Gtk.Label(label=name, xalign=0)
            box.append(lbl)
            row.set_child(box)
            row._collector = collector
            row._section_name = name
            self._cat_list.append(row)
            self._cat_rows.append(row)

        # Select first
        self._cat_list.select_row(self._cat_rows[0])

    def _load_all(self):
        for collector in SECTIONS:
            try:
                name, icon, data = collector()
                self._sections_data[collector] = (name, icon, data)
            except Exception as e:
                self._sections_data[collector] = (str(collector), "", {_("Error"): str(e)})
        GLib.idle_add(self._on_load_done)

    def _on_load_done(self):
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        count = sum(len(d[2]) for d in self._sections_data.values())
        self._status.set_text(_("%(time)s — %(count)d items loaded") % {"time": ts, "count": count})
        # Refresh current view
        row = self._cat_list.get_selected_row()
        if row:
            self._show_section(row._collector)

    def _on_cat_selected(self, listbox, row):
        if row is None:
            return
        self._show_section(row._collector)

    def _show_section(self, collector):
        # Clear
        while True:
            row = self._detail_list.get_row_at_index(0)
            if row is None:
                break
            self._detail_list.remove(row)

        data = self._sections_data.get(collector)
        if not data:
            row = Adw.ActionRow()
            row.set_title(_("Loading..."))
            self._detail_list.append(row)
            return

        name, icon, info = data
        self._title_widget.set_subtitle(name)

        for key, value in info.items():
            if not key and not value:
                continue  # skip empty separator
            row = Adw.ActionRow()
            row.set_title(key)
            if value:
                row.set_subtitle(str(value))
            # Copy button
            copy_btn = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER)
            copy_btn.add_css_class("flat")
            copy_btn.connect("clicked", self._on_copy_row, key, value)
            row.add_suffix(copy_btn)
            self._detail_list.append(row)

    def _on_copy_row(self, btn, key, value):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(f"{key}: {value}")
        self._status.set_text(_("Copied: %s") % key)

    def _on_copy_section(self, btn):
        row = self._cat_list.get_selected_row()
        if not row:
            return
        data = self._sections_data.get(row._collector)
        if not data:
            return
        name, _, info = data
        text = f"=== {name} ===\n"
        for k, v in info.items():
            text += f"{k}: {v}\n"
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(text)
        self._status.set_text(_("Section copied: %s") % name)

    def _on_refresh(self, btn):
        self._status.set_text(_("Refreshing..."))
        self._sections_data.clear()
        threading.Thread(target=self._load_all, daemon=True).start()

    def _on_export(self, btn):
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Export System Report"))
        dialog.set_initial_name(f"sysinfo-{platform.node()}.txt")
        dialog.save(self, None, self._on_export_done)

    def _on_export_done(self, dialog, result):
        try:
            f = dialog.save_finish(result)
            path = f.get_path()
            with open(path, "w") as fh:
                for collector in SECTIONS:
                    data = self._sections_data.get(collector)
                    if data:
                        name, _, info = data
                        fh.write(f"\n=== {name} ===\n")
                        for k, v in info.items():
                            fh.write(f"  {k}: {v}\n")
            self._status.set_text(_("Report exported to %s") % path)
        except:
            pass

    def _show_benchmark_result(self, title, results):
        """Show benchmark results in the detail list."""
        while True:
            row = self._detail_list.get_row_at_index(0)
            if row is None:
                break
            self._detail_list.remove(row)

        self._title_widget.set_subtitle(title)

        for key, value in results.items():
            row = Adw.ActionRow()
            row.set_title(key)
            row.set_subtitle(str(value))
            self._detail_list.append(row)

        self._status.set_text(_("Benchmark complete: %s") % title)


# ── Application ──────────────────────────────────────────────

class SysInfoApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None

        for name, callback in [
            ("bench-cpu", self._on_bench_cpu),
            ("bench-mem", self._on_bench_mem),
            ("bench-disk", self._on_bench_disk),
            ("copy-debug", self._on_copy_debug),
            ("shortcuts", self._on_shortcuts),
            ("about", self._on_about),
            ("quit", self._on_quit),
        ]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        self.set_accels_for_action("app.quit", ["<Ctrl>q"])
        self.set_accels_for_action("app.shortcuts", ["<Ctrl>slash"])

    def do_activate(self):
        if not self.window:
            self.window = SysInfoWindow(self)
        self.window.present()

    def _run_bench(self, title, bench_func):
        if not self.window:
            return
        self.window._status.set_text(_("Running benchmark: %s...") % title)

        def run():
            results = bench_func()
            GLib.idle_add(self.window._show_benchmark_result, title, results)

        threading.Thread(target=run, daemon=True).start()

    def _on_bench_cpu(self, *_):
        self._run_bench(_("CPU Benchmark"), run_benchmark_cpu)

    def _on_bench_mem(self, *_):
        self._run_bench(_("Memory Benchmark"), run_benchmark_memory)

    def _on_bench_disk(self, *_):
        self._run_bench(_("Disk Benchmark"), run_benchmark_disk)

    def _on_copy_debug(self, *_):
        if not self.window:
            return
        from . import __version__
        info = (
            f"SysInfo GTK {__version__}\n"
            f"Python {sys.version}\n"
            f"GTK {Gtk.MAJOR_VERSION}.{Gtk.MINOR_VERSION}\n"
            f"Adw {Adw.MAJOR_VERSION}.{Adw.MINOR_VERSION}\n"
            f"OS: {platform.platform()}\n"
            f"Host: {platform.node()}\n"
        )
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(info)
        self.window._status.set_text(_("Debug info copied"))

    def _on_shortcuts(self, *_):
        if self.window:
            dialog = Gtk.ShortcutsWindow(transient_for=self.window)
            section = Gtk.ShortcutsSection(visible=True)
            group = Gtk.ShortcutsGroup(title=_("General"), visible=True)
            for accel, title in [
                ("<Ctrl>q", _("Quit")),
                ("<Ctrl>slash", _("Keyboard shortcuts")),
            ]:
                group.append(Gtk.ShortcutsShortcut(accelerator=accel, title=title, visible=True))
            section.append(group)
            dialog.append(section)
            dialog.present()

    def _on_about(self, *_):
        from . import __version__
        dialog = Adw.AboutDialog(
            application_name=_("System Information"),
            application_icon="computer-symbolic",
            version=__version__,
            developer_name="Daniel Nylander",
            website="https://github.com/yeager/sysinfo-gtk",
            license_type=Gtk.License.GPL_3_0,
            issue_url="https://github.com/yeager/sysinfo-gtk/issues",
            comments=_("System information and benchmark tool. A modern GTK4/Adwaita alternative to hardinfo2."),
        )
        dialog.present(self.window)

    def _on_quit(self, *_):
        self.quit()


def main():
    app = SysInfoApp()
    app.run(sys.argv)
