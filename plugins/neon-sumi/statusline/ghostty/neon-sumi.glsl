// Neon Sumi for Ghostty -- neon tubes on an ink-wash scroll, lit for real.
//
// What it does, in the order it happens:
//   1. Neon bloom: only saturated, bright pixels glow (bars, links, state),
//      never paper-coloured prose. A tight core plus a wide halo, both
//      breathing very slightly ("hum"), the way a real tube does.
//   2. Current: a faint wave travels along everything that is neon.
//   3. Sumi paper: the background gets a static ink-wash grain and a soft
//      vignette, so the black reads as paper, not as a void.
//   4. Cursor comet: when the cursor jumps, a short magenta streak follows it.
//
// Ghostty adds its own header (GLSL 430, the uniforms, main()), so this file
// is only mainImage() plus helpers. The same body runs in the preview page
// under WebGL2; nothing below is version-specific.
//
// Turn any effect off by setting its constant to 0.0.

const float BLOOM      = 0.80;  // overall glow strength
const float CORE_PX    = 3.5;   // tight glow radius, physical pixels
const float HALO_PX    = 14.0;  // wide halo radius, physical pixels
const float HUM        = 0.035; // breathing amplitude of the glow
const float CURRENT    = 0.06;  // brightness wave along neon pixels
const float GRAIN      = 0.020; // ink-wash grain on the background
const float VIGNETTE   = 0.16;  // corner darkening
const float COMET      = 1.0;   // cursor streak strength
const float COMET_TIME = 0.28;  // seconds the streak lasts

const int CORE_TAPS = 8;
const int HALO_TAPS = 24;

// How "neon" a colour is: high chroma and high brightness. Paper (232,220,198)
// has almost no chroma, the stone and ink greys none, so they never bloom.
float neon(vec3 c) {
    float mx = max(c.r, max(c.g, c.b));
    float mn = min(c.r, min(c.g, c.b));
    return smoothstep(0.30, 0.70, mx - mn) * smoothstep(0.45, 0.90, mx);
}

vec3 gather(vec2 uv, float radius, int taps) {
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int i = 0; i < 32; i++) {
        if (i >= taps) break;
        float fi = float(i);
        float r = sqrt((fi + 0.5) / float(taps)) * radius;
        float a = fi * 2.39996323;                      // golden angle spiral
        vec2 off = vec2(cos(a), sin(a)) * r / iResolution.xy;
        vec3 s = texture(iChannel0, uv + off).rgb;
        float w = exp(-(r * r) / (radius * radius * 0.5));
        acc += s * neon(s) * w;
        wsum += w;
    }
    return acc / max(wsum, 1e-4);
}

float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
               mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

// Distance from p to the segment a-b.
float segment(vec2 p, vec2 a, vec2 b) {
    vec2 pa = p - a;
    vec2 ba = b - a;
    float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-4), 0.0, 1.0);
    return length(pa - ba * h);
}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;
    vec4 base = texture(iChannel0, uv);
    vec3 col = base.rgb;

    // 2. current along the tubes
    float n = neon(col);
    col *= 1.0 + CURRENT * n * sin(fragCoord.x * 0.035 - iTime * 1.7);

    // 1. bloom: core + halo, the halo leaning slightly towards magenta
    float hum = 1.0 + HUM * sin(iTime * 2.1) + HUM * 0.6 * sin(iTime * 5.3 + 1.7);
    vec3 core = gather(uv, CORE_PX, CORE_TAPS);
    vec3 halo = gather(uv, HALO_PX, HALO_TAPS);
    halo *= vec3(1.05, 0.92, 1.08);
    col += (core * 0.9 + halo * 1.6) * BLOOM * hum;

    // 3. sumi paper: grain and wash only where the screen is background
    float isBg = 1.0 - smoothstep(0.02, 0.10, distance(base.rgb, iBackgroundColor));
    float wash = vnoise(fragCoord / 180.0) * 0.6 + vnoise(fragCoord / 47.0) * 0.4;
    float grain = hash(floor(fragCoord)) - 0.5;
    col += isBg * GRAIN * (grain * 0.6 + (wash - 0.5) * 1.4);
    vec2 q = uv - 0.5;
    col *= 1.0 - VIGNETTE * pow(clamp(length(q) * 1.35, 0.0, 1.0), 2.4);

    // 4. cursor comet: iCurrentCursor.xy is the top-left corner, height runs down
    float since = iTime - iTimeCursorChange;
    if (COMET > 0.0 && since < COMET_TIME) {
        vec2 cur = iCurrentCursor.xy + vec2(iCurrentCursor.z * 0.5, -iCurrentCursor.w * 0.5);
        vec2 prv = iPreviousCursor.xy + vec2(iPreviousCursor.z * 0.5, -iPreviousCursor.w * 0.5);
        float fade = 1.0 - since / COMET_TIME;
        float d = segment(fragCoord, prv, cur);
        float t = clamp(dot(fragCoord - prv, cur - prv) / max(dot(cur - prv, cur - prv), 1e-4), 0.0, 1.0);
        float width = iCurrentCursor.w * 0.42 * (0.35 + 0.65 * t);
        float body = 1.0 - smoothstep(width - 1.5, width + 1.5, d);
        float glow = exp(-max(d - width, 0.0) / 9.0) * 0.45;
        vec3 cc = iCurrentCursorColor.rgb;
        col = mix(col, cc, body * fade * t * 0.85 * COMET);
        col += cc * glow * fade * t * COMET;
    }

    fragColor = vec4(col, base.a);
}
