# Probeserver Ubuntu 24.04 LTS (Python 3.12, PostgreSQL 16, Apache) mit systemd - nur für
# pruefung/linux/pruefen.sh. Pakete wie in docs/installation-linux.md, Abschnitt „Pakete“.
FROM ubuntu:24.04
ENV container=docker DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends systemd systemd-sysv dbus ca-certificates curl openssl procps \
       python3 python3-venv postgresql postgresql-client apache2 \
    && rm -rf /var/lib/apt/lists/* \
    && systemctl mask getty.target console-getty.service systemd-logind.service \
       systemd-binfmt.service proc-sys-fs-binfmt_misc.automount proc-sys-fs-binfmt_misc.mount \
    && a2dissite -q 000-default
# systemd-binfmt würde die Emulations-Handler des Docker-Hosts zurücksetzen (privilegierter Container)
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
