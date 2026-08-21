#!/usr/bin/env bash

ccache_stats_parse() {
  local raw="$1"
  local parsed

  parsed=$(printf '%s\n' "$raw" | awk '
    function set_value(name, value) {
      if (value != "" && values[name] == "") values[name] = value
    }
    /^[[:space:]]*[Cc]ache hit \(direct\)[[:space:]:]/ {
      set_value("direct", $NF)
      next
    }
    /^[[:space:]]*[Dd]irect:[[:space:]]*/ {
      value = $0
      sub(/^[^:]*:[[:space:]]*/, "", value)
      set_value("direct", value)
      next
    }
    /^[[:space:]]*[Cc]ache hit \(preprocessed\)[[:space:]:]/ {
      set_value("preprocessed", $NF)
      next
    }
    /^[[:space:]]*[Pp]reprocessed:[[:space:]]*/ {
      value = $0
      sub(/^[^:]*:[[:space:]]*/, "", value)
      set_value("preprocessed", value)
      next
    }
    /^[[:space:]]*[Cc]ache miss[[:space:]:]/ {
      set_value("misses", $NF)
      next
    }
    /^[[:space:]]*[Mm]isses:[[:space:]]*/ {
      value = $0
      sub(/^[^:]*:[[:space:]]*/, "", value)
      set_value("misses", value)
      next
    }
    /^[[:space:]]*[Cc]ache hit rate[[:space:]]+/ {
      value = $0
      sub(/^.*[Cc]ache hit rate[[:space:]]+/, "", value)
      gsub(/[[:space:]]*%.*$/, "", value)
      set_value("rate", value "%")
      next
    }
    /^[[:space:]]*[Hh]its:[[:space:]]*[0-9]+[[:space:]]*\// {
      value = $NF
      gsub(/[^0-9.]/, "", value)
      set_value("rate", value "%")
      next
    }
    /^[[:space:]]*[Cc]ache size[[:space:]]*\(GB\):/ {
      value = $0
      sub(/^.*:[[:space:]]*/, "", value)
      match(value, /^[0-9]+([.][0-9]+)?/)
      if (RSTART > 0) value = substr(value, RSTART, RLENGTH)
      set_value("size", value)
      next
    }
    /^[[:space:]]*[Cc]ache size[[:space:]]+[0-9.]+[[:space:]]+[KMGT]i?B/ {
      value = $(NF - 1)
      unit = toupper($NF)
      if (unit == "KB") value = value / 1000000
      else if (unit == "MB") value = value / 1000
      else if (unit == "TB") value = value * 1000
      else if (unit == "MIB") value = value / 1024
      else if (unit == "KIB") value = value / 1048576
      else if (unit == "TIB") value = value * 1024
      set_value("size", sprintf("%.2f", value))
      next
    }
    END {
      if (values["rate"] == "" && values["direct"] ~ /^[0-9]+$/ &&
          values["preprocessed"] ~ /^[0-9]+$/ && values["misses"] ~ /^[0-9]+$/) {
        hits = values["direct"] + values["preprocessed"]
        total = hits + values["misses"]
        if (total > 0) values["rate"] = sprintf("%.2f%%", hits / total * 100)
      }
      printf "%s\t%s\t%s\t%s\t%s\n", values["direct"], values["preprocessed"],
        values["misses"], values["rate"], values["size"]
    }
  ')

  IFS=$'\t' read -r CCACHE_STATS_HITS_DIRECT CCACHE_STATS_HITS_PREPROCESSED \
    CCACHE_STATS_MISSES CCACHE_STATS_HIT_RATE CCACHE_STATS_SIZE_GB <<< "$parsed"

  CCACHE_STATS_HITS_DIRECT=${CCACHE_STATS_HITS_DIRECT:-N/A}
  CCACHE_STATS_HITS_PREPROCESSED=${CCACHE_STATS_HITS_PREPROCESSED:-N/A}
  CCACHE_STATS_MISSES=${CCACHE_STATS_MISSES:-N/A}
  CCACHE_STATS_HIT_RATE=${CCACHE_STATS_HIT_RATE:-N/A}
  CCACHE_STATS_SIZE_GB=${CCACHE_STATS_SIZE_GB:-N/A}

  if [ "$CCACHE_STATS_HITS_DIRECT" = "N/A" ] \
    && [ "$CCACHE_STATS_HITS_PREPROCESSED" = "N/A" ] \
    && [ "$CCACHE_STATS_MISSES" = "N/A" ]; then
    CCACHE_STATS_AVAILABLE=false
  else
    CCACHE_STATS_AVAILABLE=true
  fi
}