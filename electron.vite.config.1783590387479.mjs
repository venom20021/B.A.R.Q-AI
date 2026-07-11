// electron.vite.config.ts
import { resolve } from "path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "tailwindcss";
var __electron_vite_injected_dirname = "D:\\Project\\B.A.R.Q";
var electron_vite_config_default = defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: {
          index: resolve(__electron_vite_injected_dirname, "src/main/index.ts")
        }
      }
    }
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: {
          index: resolve(__electron_vite_injected_dirname, "src/preload/index.ts"),
          overlay: resolve(__electron_vite_injected_dirname, "src/preload/overlay.ts")
        }
      }
    }
  },
  renderer: {
    root: resolve(__electron_vite_injected_dirname, "src/renderer"),
    build: {
      rollupOptions: {
        input: {
          index: resolve(__electron_vite_injected_dirname, "src/renderer/index.html"),
          overlay: resolve(__electron_vite_injected_dirname, "src/renderer/overlay.html")
        }
      }
    },
    plugins: [react()],
    css: {
      postcss: {
        plugins: [tailwindcss()]
      }
    },
    resolve: {
      alias: {
        "@": resolve(__electron_vite_injected_dirname, "src/renderer/src")
      }
    }
  }
});
export {
  electron_vite_config_default as default
};
