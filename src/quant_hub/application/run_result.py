"""Return type for scan application services."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class ServiceRunResult:
    """Outcome of a scan service run, including optional email delivery status."""

    dataframe: pd.DataFrame
    email_requested: bool = False
    email_sent: bool = False

    @property
    def ok(self) -> bool:
        """True when the run succeeded and email (if requested) was delivered."""
        if not self.email_requested:
            return True
        return self.email_sent

    @property
    def email_ok(self) -> bool:
        """Alias for email delivery success when email was requested."""
        return self.ok

    def exit_code(self) -> int:
        return 0 if self.ok else 1
