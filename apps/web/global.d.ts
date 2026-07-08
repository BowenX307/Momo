/// <reference types="next" />

declare namespace NodeJS {
  interface ProcessEnv {
    readonly NEXT_PUBLIC_API_BASE?: string;
  }
}

declare var process: {
  readonly env: NodeJS.ProcessEnv;
};
