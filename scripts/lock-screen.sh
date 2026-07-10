#!/usr/bin/env bash
set -euo pipefail

config_dir="$(cd -- "$(dirname -- "$0")/.." && pwd)"
wallpaper_config="${XDG_CONFIG_HOME:-$HOME/.config}/niri/config.kdl"
cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/swaylock"
blurred_wallpaper="$cache_dir/wallpaper-blurred.png"

wallpaper=""
if [[ -f "$wallpaper_config" ]]; then
    wallpaper="$(sed -n 's/.*spawn-at-startup "swaybg" "-i" "\([^"]*\)".*/\1/p' "$wallpaper_config" | tail -n 1)"
fi

if [[ -n "$wallpaper" && -f "$wallpaper" ]]; then
    mkdir -p "$cache_dir"

    if [[ -f "$blurred_wallpaper" && "$blurred_wallpaper" -nt "$wallpaper" ]]; then
        exec swaylock -f --config "$config_dir/swaylock.conf" --image "$blurred_wallpaper" --scaling fill "$@"
    fi

    # Não atrasa a tela de bloqueio ao trocar de wallpaper. O cache é usado na
    # próxima execução, quando a imagem desfocada já estiver pronta.
    cache_file="${blurred_wallpaper}.tmp"
    (
        magick "$wallpaper" -resize 25% -blur 0x12 -resize 400% "$cache_file" \
            && mv -f "$cache_file" "$blurred_wallpaper"
    ) &

    exec swaylock -f --config "$config_dir/swaylock.conf" --image "$wallpaper" --scaling fill "$@"
fi

exec swaylock -f --config "$config_dir/swaylock.conf" "$@"
