"""Combine a model guard and a domain UI scope without changing lock evidence."""

from contextlib import ExitStack


class CombinedMutationGuard:
    def __init__(self, model_guard, domain_scope):
        self.model_guard = model_guard
        self.domain_scope = domain_scope
        self.stack = ExitStack()

    @property
    def evidence(self):
        return self.model_guard.evidence

    def __enter__(self):
        try:
            self.stack.enter_context(self.model_guard)
            self.stack.enter_context(self.domain_scope)
        except BaseException:
            self.stack.close()
            raise
        return self

    def __exit__(self, *arguments):
        return self.stack.__exit__(*arguments)
