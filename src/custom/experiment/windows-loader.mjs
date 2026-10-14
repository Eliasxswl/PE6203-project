// Normalize Windows absolute import specifiers without changing archived tool code.
import { registerHooks } from 'node:module';
import { pathToFileURL } from 'node:url';

if (process.platform === 'win32') {
  registerHooks({
    resolve(specifier, context, nextResolve) {
      const normalized = /^[A-Za-z]:[\\/]/.test(specifier)
        ? pathToFileURL(specifier).href : specifier;
      return nextResolve(normalized, context);
    },
  });
}
