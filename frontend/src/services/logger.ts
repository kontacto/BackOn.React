// Logs técnicos apenas em desenvolvimento (__DEV__). Nunca expostos ao usuário final.
export function devLog(...args: unknown[]): void {
  if (__DEV__) {
    // eslint-disable-next-line no-console
    console.log("[biometria]", ...args);
  }
}
