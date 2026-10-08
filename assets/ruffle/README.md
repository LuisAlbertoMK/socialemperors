# Ruffle (vendored)

The Ruffle web player, bundled so the Ruffle path (`/ruffle.html`) also works with
no internet access. `templates/ruffle.html` loads `ruffle.js` from here and only
falls back to the CDN when this copy is missing.

| file | sha256 (first 16) | size |
| --- | --- | --- |
| `ruffle.js` | `26036a94567088df` | 0.44 MB |
| `172de42e6619eac8f371.wasm` | `1ed33b9b71a6b01b` | 13.64 MB |
| `878d548199cddef07035.wasm` | `af9b6a13a8f5e8d3` | 13.57 MB |

- Version **0.7.1**, taken from `https://unpkg.com/@ruffle-rs/ruffle@0.7.1/`.
- License: MIT OR Apache-2.0, see
  <https://github.com/ruffle-rs/ruffle/blob/master/LICENSE.md>. The npm tarball
  does not ship the license text, which is why it is referenced rather than copied.
- Both `.wasm` files are needed: `ruffle.js` probes the browser's WebAssembly
  features (SIMD and others) and picks one of the two.
- Keep the three files together in this directory. `ruffle.js` resolves the
  `.wasm` path relative to its own script URL (`document.currentScript.src`), so
  moving the JavaScript away from the binaries breaks the player.
