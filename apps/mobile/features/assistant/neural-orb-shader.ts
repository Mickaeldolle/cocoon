/** Bounded cost per pixel; no per-particle React updates. */
export const neuralOrbShader = `
uniform float size;
uniform float time;
uniform float energy;
half4 main(float2 xy) {
  float2 p = (xy - float2(size * 0.5)) / (size * 0.35);
  float t = time;
  float angle = atan(p.y, p.x);
  float wave = 0.024 * sin(angle * 5.0 + t * 0.7) + 0.014 * sin(angle * 8.0 - t * 0.45);
  p /= 1.0 + wave * (1.0 + energy * 0.5);
  float r = length(p);
  float edge = exp(-abs(r - 1.0) * 38.0);
  float haze = exp(-r * r * 2.7) * 0.12;
  float3 col = float3(0.42, 0.22, 0.9) * (haze + edge * 0.85);
  float alpha = haze + edge * 0.68;
  float rim = exp(-abs(r - 1.0) * 130.0) * (0.35 + 0.15 * sin(angle * 3.0 - t * 0.3));
  col += float3(0.85, 0.55, 1.0) * rim;
  alpha += rim;
  if (r < 1.0) {
    float z = sqrt(max(0.0, 1.0 - dot(p, p)));
    float lat = asin(clamp(p.y, -0.999, 0.999));
    float lon = atan(p.x, z) + t * 0.09;
    // Travelling waves move the lattice across the spherical surface.
    float u = lon + 0.085 * sin(lat * 7.0 - t * 0.65) + 0.035 * sin(lon * 9.0 + lat * 4.0 + t * 0.4);
    float v = lat + 0.065 * sin(lon * 6.0 + t * 0.55) + 0.026 * sin(lat * 11.0 - t * 0.8);
    float2 cell = fract(float2(u, v) * 15.0) - 0.5;
    float dots = exp(-dot(cell, cell) * 65.0);
    float ripple = 0.55 + 0.45 * sin(lon * 8.0 + lat * 5.0 - t * 0.8);
    float depth = 0.3 + 0.7 * z;
    float3 purple = mix(float3(0.42, 0.3, 1.0), float3(0.86, 0.42, 1.0), ripple);
    col += mix(purple, float3(0.95, 0.85, 1.0), ripple * 0.6) * dots * depth * (2.4 + energy * 0.5);
    alpha += dots * depth * 1.8;
    // Crossing curved filaments with bright junctions suggest a neural network.
    float a = abs(sin(lon * 4.0 + lat * 3.0 + 0.48 * sin(lat * 4.0 + t * 0.22)));
    float b = abs(sin(lon * 3.0 - lat * 5.0 + 0.35 * sin(lon * 5.0 - t * 0.18)));
    float filament = exp(-min(a, b) * (25.0 - energy * 6.0));
    float node = exp(-(a * a + b * b) * 1800.0);
    // The current follows the filaments; the active state broadens and brightens it.
    float travel = fract(lat * 0.28 + lon * 0.12 - t * (0.11 + energy * 0.16));
    float packet = exp(-pow((travel - 0.5) * 24.0, 2.0));
    float spark = pow(0.5 + 0.5 * sin(lon * 11.0 + lat * 7.0 - t * (1.1 + energy * 1.5)), 6.0);
    float current = filament * (0.38 + energy * 0.35 + packet * (1.5 + energy * 1.6) + spark * energy * 0.65);
    col += float3(0.61, 0.51, 1.0) * current * depth * (1.4 + energy * 0.85);
    col += float3(0.85, 0.8, 1.0) * node * (0.35 + packet * (0.5 + energy * 0.6));
    alpha += current * 1.2 + node * 0.45;
    float2 centre = p - float2(0.08 * sin(t * 0.3), 0.06);
    float core = exp(-dot(centre, centre) * 16.0);
    col += float3(0.62, 0.32, 0.95) * core * 0.65;
    alpha += core * 0.5;
  }
  float fade = 1.0 - smoothstep(1.02, 1.28, r);
  alpha = clamp(alpha * fade, 0.0, 0.94);
  // Premultiplied alpha keeps transparent edges correct in both themes.
  return half4(min(clamp(col * fade, 0.0, 1.0), float3(alpha)), alpha);
}
`;
