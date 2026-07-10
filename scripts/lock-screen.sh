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
    # Reduzir antes de desfocar mantém o bloqueio ágil mesmo com wallpapers 4K/6K.
    if magick "$wallpaper" -resize 25% -blur 0x12 -resize 400% "$blurred_wallpaper"; then
        swaylock -f --config "$config_dir/swaylock.conf" --image "$blurred_wallpaper" --scaling fill "$@"
        exit
    fi
fi

swaylock -f --config "$config_dir/swaylock.conf" "$@"
