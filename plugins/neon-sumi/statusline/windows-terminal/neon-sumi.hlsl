// Neon Sumi for Windows Terminal -- the Ghostty shader (ghostty/neon-sumi.glsl)
// ported to HLSL for Windows Terminal's "experimental.pixelShaderPath".
//
// What it does, in the order it happens:
//   1. Neon bloom: only saturated, bright pixels glow (bars, links, state),
//      never paper-coloured prose. A tight core plus a wide halo, both
//      breathing very slightly ("hum"), the way a real tube does.
//   2. Current: a faint wave travels along everything that is neon.
//   3. Sumi paper: the background gets a static ink-wash grain and a soft
//      vignette, so the black reads as paper, not as a void.
//
// The Ghostty cursor comet is not here: Windows Terminal gives a shader no
// cursor position. Everything else matches the GLSL constants one to one.
//
// Turn any effect off by setting its constant to 0.0. Toggle the whole shader
// at runtime with the toggleShaderEffects action.

Texture2D shaderTexture;
SamplerState samplerState;

cbuffer PixelShaderSettings {
    float  Time;        // seconds since the shader loaded
    float  Scale;       // UI scale
    float2 Resolution;  // size of shaderTexture, physical pixels
    float4 Background;  // background colour, rgba
};

static const float BLOOM    = 0.80;  // overall glow strength
static const float CORE_PX  = 3.5;   // tight glow radius, physical pixels
static const float HALO_PX  = 14.0;  // wide halo radius, physical pixels
static const float HUM      = 0.035; // breathing amplitude of the glow
static const float CURRENT  = 0.06;  // brightness wave along neon pixels
static const float GRAIN    = 0.020; // ink-wash grain on the background
static const float VIGNETTE = 0.16;  // corner darkening

#define CORE_TAPS 8
#define HALO_TAPS 24

// How "neon" a colour is: high chroma and high brightness. Paper (232,220,198)
// has almost no chroma, the stone and ink greys none, so they never bloom.
float neon(float3 c) {
    float mx = max(c.r, max(c.g, c.b));
    float mn = min(c.r, min(c.g, c.b));
    return smoothstep(0.30, 0.70, mx - mn) * smoothstep(0.45, 0.90, mx);
}

float3 gather(float2 uv, float radius, int taps) {
    float3 acc = float3(0.0, 0.0, 0.0);
    float wsum = 0.0;
    [unroll]
    for (int i = 0; i < taps; i++) {
        float fi = (float)i;
        float r = sqrt((fi + 0.5) / (float)taps) * radius;
        float a = fi * 2.39996323;                      // golden angle spiral
        float2 off = float2(cos(a), sin(a)) * r / Resolution;
        float3 s = shaderTexture.SampleLevel(samplerState, uv + off, 0).rgb;
        float w = exp(-(r * r) / (radius * radius * 0.5));
        acc += s * neon(s) * w;
        wsum += w;
    }
    return acc / max(wsum, 1e-4);
}

float hash(float2 p) {
    p = frac(p * float2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return frac(p.x * p.y);
}

float vnoise(float2 p) {
    float2 i = floor(p);
    float2 f = frac(p);
    float2 u = f * f * (3.0 - 2.0 * f);
    return lerp(lerp(hash(i), hash(i + float2(1.0, 0.0)), u.x),
                lerp(hash(i + float2(0.0, 1.0)), hash(i + float2(1.0, 1.0)), u.x), u.y);
}

float4 main(float4 pos : SV_POSITION, float2 tex : TEXCOORD) : SV_TARGET {
    float2 uv = tex;
    float2 fragCoord = tex * Resolution;
    float4 base = shaderTexture.SampleLevel(samplerState, uv, 0);
    float3 col = base.rgb;

    // 2. current along the tubes
    float n = neon(col);
    col *= 1.0 + CURRENT * n * sin(fragCoord.x * 0.035 - Time * 1.7);

    // 1. bloom: core + halo, the halo leaning slightly towards magenta
    float hum = 1.0 + HUM * sin(Time * 2.1) + HUM * 0.6 * sin(Time * 5.3 + 1.7);
    float3 core = gather(uv, CORE_PX, CORE_TAPS);
    float3 halo = gather(uv, HALO_PX, HALO_TAPS);
    halo *= float3(1.05, 0.92, 1.08);
    col += (core * 0.9 + halo * 1.6) * BLOOM * hum;

    // 3. sumi paper: grain and wash only where the screen is background
    float isBg = 1.0 - smoothstep(0.02, 0.10, distance(base.rgb, Background.rgb));
    float wash = vnoise(fragCoord / 180.0) * 0.6 + vnoise(fragCoord / 47.0) * 0.4;
    float grain = hash(floor(fragCoord)) - 0.5;
    col += isBg * GRAIN * (grain * 0.6 + (wash - 0.5) * 1.4);
    float2 q = uv - 0.5;
    col *= 1.0 - VIGNETTE * pow(saturate(length(q) * 1.35), 2.4);

    return float4(col, base.a);
}
