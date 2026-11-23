"""End-User License Agreement and Privacy Policy. Public, no login.

Thomas, 2026-11-23. Intuit's production review for the QuickBooks
connection asks for an EULA URL and a privacy policy URL, and its reviewers
open them without a Hub login. These two routes have no login decorator on
purpose. They hold no data and read nothing.

The text is Thomas's own, written 2026-08-03 for the laptop QuickBooks
client (business-intel/qb_reports/qbo_client/legal/), never published.
The only change when it moved here: the company name read "Premier
Property Solutions"; it is Pure Property Solutions. Edit the files in
templates/legal/ if the wording changes.
"""

from __future__ import annotations


def register_routes(app):
    from flask import render_template

    @app.route('/eula')
    def legal_eula():
        return render_template('legal/eula.html')

    @app.route('/privacy-policy')
    def legal_privacy():
        return render_template('legal/privacy-policy.html')
