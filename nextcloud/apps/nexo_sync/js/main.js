(() => {
    const bindDialog = (dialogId, buttonId) => {
        const dialog = document.getElementById(dialogId);
        const openButton = document.getElementById(buttonId);
        if (!dialog || !openButton) {
            return null;
        }
        const open = () => {
            if (!dialog.open) {
                dialog.showModal();
            }
        };
        openButton.addEventListener('click', open);
        dialog.querySelector('[data-close-dialog]').addEventListener('click', () => dialog.close());
        return open;
    };

    const init = () => {
        const openUsers = bindDialog('nx-assistant-users', 'nx-open-assistant-users');
        bindDialog('nx-sectors', 'nx-open-sectors');
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
