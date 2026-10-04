#!/bin/sh
# Claude Code subagent status line - one row per running subagent.
# Wired up via "subagentStatusLine" in settings.json.
#
# Identity on the left, pressure pinned right. Model and effort chips appear
# only when they differ from NEON_SUMI_EXPECT_MODEL / NEON_SUMI_EXPECT_EFFORT;
# leave those unset to always show them. Same palette and thresholds as the
# main line (amber at 70 %, red at 85 %); a finished task never alarms, and the
# label shortens so a row fits the width Claude Code gives it.
#
# Preview:
#   sh subagent.sh < probe.json

LC_ALL=${LC_ALL:-en_US.UTF-8}
export LC_ALL

EXPECT_MODEL="${NEON_SUMI_EXPECT_MODEL:-}"
EXPECT_EFFORT="${NEON_SUMI_EXPECT_EFFORT:-}"
WARN=70
CRIT=85

now=$(date +%s)

# A non-zero exit makes Claude Code discard every row, so never fail loudly.
jq -c \
  --argjson now "$now" \
  --arg expect_model "$EXPECT_MODEL" \
  --arg expect_effort "$EXPECT_EFFORT" \
  --argjson warn "$WARN" \
  --argjson crit "$CRIT" '

  def esc: [27] | implode;
  def sgr(c): esc + "[" + c + "m";
  def off: esc + "[0m";

  def rgb($r; $g; $b): sgr("38;2;\($r);\($g);\($b)");
  def bright: rgb(232; 220; 198);
  def dim:    rgb(146; 134; 120);
  def faint:  rgb(115; 104; 95);
  def warnc:  rgb(255; 190; 40);
  def critc:  sgr("1") + rgb(255; 56; 100);

  def tone(p): if p >= $crit then critc elif p >= $warn then warnc else dim end;

  def clip(n): if (length <= n) then . else (.[0:n-1] + "…") end;

  def elapsed(s):
    ($now - s) as $d
    | if   $d < 0     then ""
      elif $d < 3600  then (($d / 60) | floor | tostring) + "m"
      else (($d / 3600) | floor | tostring) + "h"
           + ((($d % 3600) / 60) | floor | tostring) + "m"
      end;

  (.columns // 120) as $cols
  | .tasks[]?
  | . as $t
  | (.contextWindowSize // 0) as $w
  | (if $w > 0 then (((.tokenCount // 0) * 100 / $w) | floor) else -1 end) as $pct
  | (if   .status == "running"   then ["◐", dim]
     elif .status == "completed" then ["✓", faint]
     elif .status == "failed"    then ["✗", critc]
     else                             ["·", faint] end) as $mark

  | ([ (if $expect_model == "" or (.model // $expect_model) != $expect_model then (.model | sub("^claude-"; "")) else empty end),
       (if .effort != null and ($expect_effort == "" or .effort != $expect_effort) then ("effort " + .effort) else empty end)
     ] | join("  ")) as $chips

  | (if $pct >= 0 then ($pct | tostring) + "%" else "" end) as $ctx
  | elapsed((.startTime // 0) / 1000 | floor) as $age
  | (if .status == "running" then tone($pct) else faint end) as $ctone

  | ([$chips, $ctx, $age] | map(select(. != "")) | join("   ")) as $right_p
  | ($cols - ($right_p | length) - 5) as $room
  | ((.label // .name // "agent") | clip(if $room < 12 then 12 elif $room < 40 then $room else 40 end)) as $lbl

  | ($mark[0] + " " + $lbl) as $left_p
  | ($mark[1] + $mark[0] + off + " " + dim + $lbl + off) as $left_c

  | ([ (if $chips != "" then faint + $chips + off else empty end),
       (if $ctx   != "" then $ctone + $ctx + off else empty end),
       (if $age   != "" then faint + $age + off else empty end)
     ] | join("   ")) as $right_c

  | ($cols - ($left_p | length) - ($right_p | length)) as $gap
  | (if $gap > 0 then (" " * $gap) else "  " end) as $pad

  | { id: $t.id, content: ($left_c + $pad + $right_c) }
' 2>/dev/null || exit 0
