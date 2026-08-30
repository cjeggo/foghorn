#!/usr/bin/env sh
# One-time setup for the WordPress test targets after `podman compose up`.
# Completes each install and pins siteurl/home to the container hostname so
# wpscan (which reaches them by that name over the demo network) isn't 301'd
# away. Idempotent-ish: re-running just re-pins the URLs.
set -e

setup() {
  wp_ctr="$1"; db_ctr="$2"; db_name="$3"; db_user="$4"; db_pass="$5"; host_port="$6"
  echo "== $wp_ctr =="
  curl -s -o /dev/null \
    -d "weblog_title=ReconLab&user_name=admin&admin_password=Recon-Lab-Adm1n-2026&admin_password2=Recon-Lab-Adm1n-2026&pw_weak=1&admin_email=admin@recon.lab&blog_public=1&Submit=Install+WordPress&language=" \
    "http://127.0.0.1:${host_port}/wp-admin/install.php?step=2" || true
  podman exec "$db_ctr" mariadb -u"$db_user" -p"$db_pass" "$db_name" \
    -e "UPDATE wp_options SET option_value='http://${wp_ctr}' WHERE option_name IN ('siteurl','home');"
  podman exec "$wp_ctr" sh -c "sed -i '/WP_SITEURL\|WP_HOME/d' /var/www/html/wp-config.php" || true
  echo "   pinned siteurl -> http://${wp_ctr}"
}

setup wordpress      wp-mariadb  wordpress wp wppass 8083
setup wordpress-vuln wp-vuln-db  wp        wp wp     8084

# Docker Hub silently rebuilds the wordpress:4.7.1 tag with the latest 4.7.x
# security patches (serves 4.7.35, zero known CVEs). Overlay the frozen 4.7.0
# release archive from wordpress.org to get a genuinely vulnerable core
# (CVE-2017-1001000 REST API content injection, etc).
echo "== wordpress-vuln: pinning core to unpatched 4.7.0 =="
tmp="$(mktemp -d)"
curl -s -o "$tmp/wp.zip" "https://wordpress.org/wordpress-4.7.zip"
( cd "$tmp" && unzip -q wp.zip )
podman exec wordpress-vuln sh -c 'cp /var/www/html/wp-config.php /tmp/wpc.php'
podman cp "$tmp/wordpress/." wordpress-vuln:/var/www/html/
podman exec wordpress-vuln sh -c 'cp /tmp/wpc.php /var/www/html/wp-config.php; chown -R www-data:www-data /var/www/html; sed -i "/WP_SITEURL\|WP_HOME/d" /var/www/html/wp-config.php'
rm -rf "$tmp"
echo "   core now 4.7.0"

echo "done. From n8n they are http://wordpress and http://wordpress-vuln"
echo "From a Kali VM: http://192.168.56.1:8083 / :8084 (add a hosts entry or"
echo "send Host: wordpress-vuln, since WP redirects to the container name)."
