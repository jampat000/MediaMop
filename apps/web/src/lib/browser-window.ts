export const browserWindow = {
  reloadCurrentPage(): void {
    const href = window.location.href;
    try {
      window.location.replace(href);
      return;
    } catch {
      // Fall through to the next navigation strategy.
    }
    try {
      window.location.assign(href);
      return;
    } catch {
      // Fall through to the final hard reload.
    }
    window.location.reload();
  },
};
