# Probeserver Rocky Linux 9 (wie RHEL 9: Python 3.12, PostgreSQL 16, Apache httpd) mit systemd –
# nur für pruefung/linux/pruefen.sh. Pakete wie in docs/installation-linux.md, Abschnitt „Pakete“ (RHEL);
# dazu python3.11 als Python vor dem Upgrade der Distribution (ablauf.sh).
FROM rockylinux/rockylinux:9
RUN dnf -y module enable postgresql:16 \
    && dnf -y install systemd procps-ng tar gzip findutils openssl \
       python3.12 python3.11 postgresql-server postgresql httpd mod_ssl mod_http2 \
    && dnf clean all \
    && systemctl mask getty.target console-getty.service systemd-logind.service \
       systemd-binfmt.service proc-sys-fs-binfmt_misc.automount proc-sys-fs-binfmt_misc.mount
# systemd-binfmt würde die Emulations-Handler der Docker-VM zurücksetzen (privilegierter Container):
# auf Apple-Rechnern fiele damit Rosetta für amd64 aus
STOPSIGNAL SIGRTMIN+3
CMD ["/usr/sbin/init"]
