// Pages hosts the interface; execution remains on the local authenticated bridge.
if (location.hostname.endsWith('.github.io')) {
  document.addEventListener('DOMContentLoaded', () => {
    const notice = document.createElement('div');
    notice.setAttribute('role', 'status');
    notice.style.cssText = 'position:fixed;bottom:12px;left:260px;right:20px;z-index:99999;padding:12px 18px;background:#17171c;border:1px solid #555;color:white;border-radius:8px;font:13px system-ui';
    notice.textContent = 'Vista online · Para conectar terminales y ejecutar operaciones, abre el panel local con INICIAR_TRADINGNOTE.bat.';
    document.body.append(notice);
  });
}
