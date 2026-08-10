import { brotliCompressSync, gzipSync } from 'node:zlib';
import { defineConfig } from 'vite';

const splitThree = process.env.TASK13B_SPLIT === 'three';
const label = splitThree ? 'three-split-experiment' : 'baseline';
const outDir = splitThree ? 'dist-task13b-split' : 'dist-task13b-baseline';

function classifyModule(id: string): 'three' | 'app' | 'other_dependency' | 'other' {
  const normalized = id.replaceAll('\\', '/');
  if (normalized.includes('/node_modules/three/')) return 'three';
  if (normalized.includes('/node_modules/')) return 'other_dependency';
  if (normalized.includes('/src/')) return 'app';
  return 'other';
}

function bundleEvidencePlugin() {
  return {
    name: 'task13b-bundle-evidence',
    generateBundle(_options: unknown, bundle: Record<string, any>) {
      const chunks = Object.values(bundle)
        .filter((item: any) => item.type === 'chunk')
        .map((chunk: any) => {
          const modules = Object.entries(chunk.modules).map(([id, info]: [string, any]) => ({
            id: id.replace(process.cwd(), '.'),
            category: classifyModule(id),
            renderedLength: Number(info.renderedLength ?? 0),
          }));

          const categories: Record<string, number> = {};
          for (const module of modules) {
            categories[module.category] = (categories[module.category] ?? 0) + module.renderedLength;
          }

          return {
            fileName: chunk.fileName,
            isEntry: chunk.isEntry,
            codeBytes: Buffer.byteLength(chunk.code),
            gzipBytes: gzipSync(chunk.code).byteLength,
            brotliBytes: brotliCompressSync(chunk.code).byteLength,
            imports: chunk.imports,
            dynamicImports: chunk.dynamicImports,
            categoryRenderedBytes: categories,
            modules,
          };
        });

      const totals = chunks.reduce(
        (acc: any, chunk: any) => {
          acc.codeBytes += chunk.codeBytes;
          acc.gzipBytes += chunk.gzipBytes;
          acc.brotliBytes += chunk.brotliBytes;
          for (const [category, bytes] of Object.entries(chunk.categoryRenderedBytes)) {
            acc.categoryRenderedBytes[category] =
              (acc.categoryRenderedBytes[category] ?? 0) + Number(bytes);
          }
          return acc;
        },
        { codeBytes: 0, gzipBytes: 0, brotliBytes: 0, categoryRenderedBytes: {} as Record<string, number> },
      );

      this.emitFile({
        type: 'asset',
        fileName: 'task13b-bundle-evidence.json',
        source: JSON.stringify(
          {
            schemaVersion: 1,
            label,
            sourceCarrierCommit: 'bf5ba41951b7d37c588ebd7abc0944a856782b2c',
            viteVersion: '8.2.1',
            splitThree,
            totals,
            chunks,
          },
          null,
          2,
        ),
      });
    },
  };
}

export default defineConfig({
  plugins: [bundleEvidencePlugin()],
  build: {
    outDir,
    emptyOutDir: true,
    rolldownOptions: splitThree
      ? {
          output: {
            codeSplitting: {
              groups: [
                {
                  name: 'three-vendor',
                  test: /node_modules[\\/]three[\\/]/,
                  priority: 20,
                },
              ],
            },
          },
        }
      : undefined,
  },
});
