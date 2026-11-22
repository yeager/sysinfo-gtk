#!/usr/bin/env python3
"""Build architecture-independent DEB and RPM packages."""
import argparse, hashlib, shutil, subprocess, tarfile, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "sysinfo-gtk"

def run(args): subprocess.run(args, check=True)
def copy_sources(dst):
    shutil.copytree(ROOT / "src/sysinfo_gtk", dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))

def build_deb(version, output):
    with tempfile.TemporaryDirectory(prefix="sysinfo-deb-") as tmp:
        root=Path(tmp)/"root"; root.mkdir()
        copy_sources(root/"usr/share/sysinfo-gtk/sysinfo_gtk")
        launcher=root/"usr/bin/sysinfo-gtk"; launcher.parent.mkdir(parents=True,exist_ok=True); launcher.write_text("#!/usr/bin/python3\nimport sys\nsys.path.insert(0, \"/usr/share/sysinfo-gtk\")\nfrom sysinfo_gtk.main import main\nmain()\n"); launcher.chmod(0o755)
        for rel,src in [("usr/share/applications/sysinfo-gtk.desktop",ROOT/"sysinfo-gtk.desktop"),("usr/share/icons/hicolor/scalable/apps/se.danielnylander.sysinfo-gtk.svg",ROOT/"data/icons/se.danielnylander.sysinfo-gtk.svg")]:
            dest=root/rel; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dest)
        mo=root/"usr/share/locale/sv/LC_MESSAGES/sysinfo-gtk.mo"; mo.parent.mkdir(parents=True,exist_ok=True); run(["msgfmt","-o",str(mo),str(ROOT/"po/sv.po")])
        control=root/"DEBIAN"; control.mkdir()
        (control/"control").write_text(f"Package: sysinfo-gtk\nVersion: {version}\nArchitecture: all\nMaintainer: Daniel Nylander <daniel@danielnylander.se>\nDepends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1\nSection: admin\nPriority: optional\nDescription: GTK4/Adwaita system information and benchmark tool\n View hardware and operating system details, run benchmarks, and export reports.\n")
        run(["dpkg-deb","--build","--root-owner-group",str(root),str(output/f"sysinfo-gtk_{version}_all.deb")])

def build_rpm(version, output):
    with tempfile.TemporaryDirectory(prefix="sysinfo-rpm-") as tmp:
        t=Path(tmp); top=t/"rpmbuild"
        for d in ("BUILD","BUILDROOT","RPMS","SOURCES","SPECS","SRPMS"): (top/d).mkdir(parents=True)
        source=t/"sysinfo_gtk"; copy_sources(source)
        with tarfile.open(top/"SOURCES/sysinfo-gtk.tar.gz","w:gz") as tf: tf.add(source,arcname="sysinfo_gtk")
        spec=f"""Name: sysinfo-gtk\nVersion: {version}\nRelease: 1%{{?dist}}\nSummary: GTK4/Adwaita system information and benchmark tool\nLicense: GPL-3.0-or-later\nBuildArch: noarch\nRequires: python3 >= 3.10\nRequires: python3-gobject\nRequires: gtk4\nRequires: libadwaita\nSource0: sysinfo-gtk.tar.gz\n\n%description\nGTK4/Adwaita application for system information, hardware details, and benchmarks.\n\n%prep\n%setup -q -n sysinfo_gtk\n\n%install\ninstall -d %{{buildroot}}%{{_datadir}}/sysinfo-gtk/sysinfo_gtk\ninstall -m 0644 *.py %{{buildroot}}%{{_datadir}}/sysinfo-gtk/sysinfo_gtk/\ninstall -d %{{buildroot}}%{{_bindir}}\ncat > %{{buildroot}}%{{_bindir}}/sysinfo-gtk <<'EOF'\n#!/usr/bin/python3\nimport sys\nsys.path.insert(0, \"/usr/share/sysinfo-gtk\")\nfrom sysinfo_gtk.main import main\nmain()\nEOF\nchmod 0755 %{{buildroot}}%{{_bindir}}/sysinfo-gtk\ninstall -D -m 0644 {ROOT}/sysinfo-gtk.desktop %{{buildroot}}%{{_datadir}}/applications/sysinfo-gtk.desktop\ninstall -D -m 0644 {ROOT}/data/icons/se.danielnylander.sysinfo-gtk.svg %{{buildroot}}%{{_datadir}}/icons/hicolor/scalable/apps/se.danielnylander.sysinfo-gtk.svg\ninstall -D -m 0644 {ROOT}/po/sv.po %{{_builddir}}/sv.po\ninstall -d %{{buildroot}}%{{_datadir}}/locale/sv/LC_MESSAGES\nmsgfmt -o %{{buildroot}}%{{_datadir}}/locale/sv/LC_MESSAGES/sysinfo-gtk.mo %{{_builddir}}/sv.po\n\n%files\n%{{_bindir}}/sysinfo-gtk\n%{{_datadir}}/sysinfo-gtk/sysinfo_gtk/\n%{{_datadir}}/applications/sysinfo-gtk.desktop\n%{{_datadir}}/icons/hicolor/scalable/apps/se.danielnylander.sysinfo-gtk.svg\n%{{_datadir}}/locale/sv/LC_MESSAGES/sysinfo-gtk.mo\n"""
        sp=top/"SPECS/sysinfo-gtk.spec"; sp.write_text(spec)
        rpmdb=t/"rpmdb"; rpmdb.mkdir()
        run(["rpmbuild","-bb","--define",f"_dbpath {rpmdb}","--define",f"_topdir {top}",str(sp)])
        built=next((top/"RPMS/noarch").glob("*.rpm")); shutil.copy2(built,output/built.name)
        header=subprocess.check_output(["rpm","--dbpath",str(rpmdb),"-qp","--qf","%{NAME} %{VERSION} %{ARCH}",str(output/built.name)],text=True)
        if header != f"sysinfo-gtk {version} noarch": raise RuntimeError(header)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--version",required=True); ap.add_argument("--output",type=Path,required=True); a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=True); build_deb(a.version,a.output); build_rpm(a.version,a.output)
    files=sorted(a.output.glob("*.deb"))+sorted(a.output.glob("*.rpm"))
    (a.output/"SHA256SUMS").write_text("".join(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}\n" for f in files))
    print(f"Built packages for {a.version}")
if __name__ == "__main__": main()
