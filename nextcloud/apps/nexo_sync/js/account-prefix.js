(() => {
	'use strict';

	const tenant = window.OCP?.InitialState?.loadState('nexo_sync', 'accountTenant', null);

	if (!tenant) {
		return;
	}

	const prefix = `${tenant}.`;
	const normalize = (input) => {
		const value = input.value.trim().toLowerCase();
		if (!value) {
			return;
		}
		const withoutPrefix = value.startsWith(prefix) ? value.slice(prefix.length) : value;
		const normalized = `${prefix}${withoutPrefix}`;
		if (input.value !== normalized) {
			const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
			setter.call(input, normalized);
			input.dispatchEvent(new Event('input', { bubbles: true }));
			input.dispatchEvent(new Event('change', { bubbles: true }));
		}
	};

	const isAccountId = (input) => {
		if (!(input instanceof HTMLInputElement) || input.type === 'hidden' || input.type === 'password') {
			return false;
		}
		const details = [input.id, input.name, input.placeholder, input.getAttribute('aria-label')]
			.concat(Array.from(input.labels || [], (label) => label.textContent || ''))
			.join(' ')
			.toLowerCase();
		return /nombre de la cuenta|account name|username|user id|userid/.test(details);
	};

	const bind = (root) => {
		root.querySelectorAll('input').forEach((input) => {
			if (!isAccountId(input) || input.dataset.nexoPrefixBound) {
				return;
			}
			input.dataset.nexoPrefixBound = '1';
			input.placeholder = input.placeholder || `Nombre corto (se añadirá ${prefix})`;
			input.addEventListener('blur', () => normalize(input));
			const form = input.closest('form');
			if (form && !form.dataset.nexoPrefixBound) {
				form.dataset.nexoPrefixBound = '1';
				form.addEventListener('submit', () => {
					form.querySelectorAll('input').forEach((candidate) => {
						if (isAccountId(candidate)) {
							normalize(candidate);
						}
					});
				}, true);
			}
		});
	};

	const observer = new MutationObserver((mutations) => {
		for (const mutation of mutations) {
			for (const node of mutation.addedNodes) {
				if (node instanceof HTMLElement) {
					if (node.matches('input')) {
						bind(node.parentElement || document);
					} else {
						bind(node);
					}
				}
			}
		}
	});

	const start = () => {
		bind(document);
		observer.observe(document.body, { childList: true, subtree: true });
	};

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', start, { once: true });
	} else {
		start();
	}
})();
