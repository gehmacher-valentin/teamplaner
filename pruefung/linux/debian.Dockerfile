# Probeserver Debian 12 (Python 3.11, PostgreSQL 15, nginx) mit systemd – nur für pruefung/linux/pruefen.sh.
# Pakete wie in docs/installation-linux.md, Abschnitt „Pakete“ (Debian/Ubuntu).
FROM debian:12
ENV container=docker DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends systemd systemd-sysv dbus ca-certificates curl openssl procps \
       python3 python3-venv postgresql postgresql-client nginx \
    && rm -rf /var/lib/apt/lists/* \
    && systemctl mask getty.target console-getty.service systemd-logind.service \
       systemd-binfmt.service proc-sys-fs-binfmt_misc.automount proc-sys-fs-binfmt_misc.mount \
    && rm -f /etc/nginx/sites-enabled/default
# systemd-binfmt würde die Emulations-Handler der Docker-VM zurücksetzen (privilegierter Container):
# auf Apple-Rechnern fiele damit Rosetta für amd64 aus
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
