"""Northwind Corp sandbox suite: four small but *real* web applications the agent operates through a browser.

  /mail      corporate webmail (inbox, message view, PDF attachments, compose/drafts/sent)
  /erp       "Ledger" accounts-payable system (bills list, create bill w/ validation + duplicate detection, pay)
  /portal    Globex vendor billing portal (login required, invoice list + PDF download)
  /helpdesk  ticketing (notes, close/reopen)
  /admin/*   reset, chaos control, ground-truth state (for tests/evals - never used by the agent)

Run:  python -m sandbox.app
"""
from __future__ import annotations

import re
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import ATTACHMENTS_DIR, SANDBOX_HOST, SANDBOX_PORT
from sandbox import chaos, db, seed

PORTAL_USER = "northwind-ap"
PORTAL_PASSWORD = "Gl0bex!Sandbox-2026"
_portal_sessions: set[str] = set()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    with db.session() as c:
        empty = c.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 0
    if empty:
        seed.reset()
    yield


app = FastAPI(title="Northwind Corp Sandbox", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(chaos.ChaosMiddleware)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def render(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    ctx.setdefault("chaos_modal", getattr(request.state, "chaos_modal", False))
    ctx.setdefault("flash", request.query_params.get("flash"))
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "home.html")


# ----------------------------------------------------------------------------- mail
@app.get("/mail", response_class=HTMLResponse)
def mail_inbox(request: Request, folder: str = "inbox", q: str = ""):
    with db.session() as c:
        sql = "SELECT * FROM emails WHERE folder=?"
        args: list = [folder]
        if q:
            sql += " AND (subject LIKE ? OR body LIKE ? OR sender_name LIKE ?)"
            args += [f"%{q}%"] * 3
        emails = db.rows(c, sql + " ORDER BY received_at DESC", *args)
    return render(request, "mail_list.html", emails=emails, folder=folder, q=q)


@app.get("/mail/message/{email_id}", response_class=HTMLResponse)
def mail_message(request: Request, email_id: int):
    with db.session() as c:
        c.execute("UPDATE emails SET is_read=1 WHERE id=?", (email_id,))
        found = db.rows(c, "SELECT * FROM emails WHERE id=?", email_id)
    if not found:
        raise HTTPException(404, "Message not found")
    return render(request, "mail_message.html", email=found[0])


@app.get("/mail/attachments/{filename}")
def mail_attachment(filename: str):
    path = ATTACHMENTS_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(404, "Attachment not found")
    return FileResponse(path, media_type="application/pdf", filename=path.name,
                        content_disposition_type="inline")


@app.get("/mail/compose", response_class=HTMLResponse)
def mail_compose(request: Request, to: str = "", subject: str = ""):
    return render(request, "mail_compose.html", to=to, subject=subject, error=None, body="")


@app.post("/mail/compose", response_class=HTMLResponse)
def mail_compose_submit(request: Request, to: str = Form(""), subject: str = Form(""), body: str = Form(""),
                        action: str = Form("draft")):
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+(\s*,\s*[^@\s]+@[^@\s]+\.[^@\s]+)*", to.strip()):
        return render(request, "mail_compose.html", to=to, subject=subject, body=body,
                      error="Please enter a valid recipient email address.", status_code=422)
    if not subject.strip():
        return render(request, "mail_compose.html", to=to, subject=subject, body=body,
                      error="Subject is required.", status_code=422)
    folder = "sent" if action == "send" else "drafts"
    with db.session() as c:
        cur = c.execute(
            "INSERT INTO emails(folder, sender_name, sender_email, recipient, subject, body, received_at, is_read) "
            "VALUES(?,?,?,?,?,?,?,1)",
            (folder, "Northwind AP", "ap@northwind.example", to.strip(), subject.strip(), body,
             datetime.now().isoformat(timespec="minutes")))
    word = "sent" if folder == "sent" else "saved to Drafts"
    return RedirectResponse(f"/mail?folder={folder}&flash=Message+{cur.lastrowid}+{word.replace(' ', '+')}",
                            status_code=303)


# ----------------------------------------------------------------------------- ERP
def _vendors() -> list[dict]:
    with db.session() as c:
        return db.rows(c, "SELECT * FROM vendors ORDER BY name")


@app.get("/erp", response_class=HTMLResponse)
def erp_home():
    return RedirectResponse("/erp/bills", status_code=302)


@app.get("/erp/bills", response_class=HTMLResponse)
def erp_bills(request: Request, status: str = "", vendor: str = ""):
    sql, args = "SELECT * FROM bills WHERE 1=1", []
    if status in ("open", "paid"):
        sql += " AND status=?"
        args.append(status)
    if status == "overdue":
        sql += " AND status='open' AND due_date < ?"
        args.append(date.today().isoformat())
    if vendor:
        sql += " AND vendor=?"
        args.append(vendor)
    with db.session() as c:
        bills = db.rows(c, sql + " ORDER BY id DESC", *args)
    today = date.today().isoformat()
    for b in bills:
        b["overdue"] = b["status"] == "open" and b["due_date"] < today
    return render(request, "erp_bills.html", bills=bills, status=status, vendor=vendor, vendors=_vendors())


@app.get("/erp/bills/new", response_class=HTMLResponse)
def erp_new_bill(request: Request):
    return render(request, "erp_new_bill.html", vendors=_vendors(), form={}, errors=[])


AMOUNT_RE = re.compile(r"^\$?\s*(\d{1,3}(,\d{3})*|\d+)(\.\d{1,2})?$")


@app.post("/erp/bills", response_class=HTMLResponse)
def erp_create_bill(request: Request, vendor: str = Form(""), invoice_number: str = Form(""),
                    amount: str = Form(""), currency: str = Form("USD"), due_date: str = Form(""),
                    notes: str = Form("")):
    form = dict(vendor=vendor, invoice_number=invoice_number.strip(), amount=amount.strip(),
                currency=currency, due_date=due_date.strip(), notes=notes)
    errors = []
    if vendor not in {v["name"] for v in _vendors()}:
        errors.append("Vendor must be selected from the vendor master list.")
    if not form["invoice_number"]:
        errors.append("Invoice number is required.")
    if not AMOUNT_RE.match(form["amount"]):
        errors.append("Amount must be a number, e.g. 1234.56")
    try:
        datetime.strptime(form["due_date"], "%Y-%m-%d")
    except ValueError:
        errors.append("Due date must be a valid date (YYYY-MM-DD).")
    if not errors:
        with db.session() as c:
            dup = c.execute("SELECT id FROM bills WHERE vendor=? AND invoice_number=?",
                            (vendor, form["invoice_number"])).fetchone()
        if dup:
            errors.append(f"Duplicate: a bill for {vendor} invoice {form['invoice_number']} already exists "
                          f"(bill B-{1000 + dup['id']}).")
    if errors:
        return render(request, "erp_new_bill.html", vendors=_vendors(), form=form, errors=errors, status_code=422)
    value = float(form["amount"].replace("$", "").replace(",", "").strip())
    with db.session() as c:
        cur = c.execute(
            "INSERT INTO bills(vendor, invoice_number, amount, currency, due_date, notes, created_at, created_by) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (vendor, form["invoice_number"], value, currency, form["due_date"], notes,
             datetime.now().isoformat(timespec="seconds"), "web"))
    bill_id = cur.lastrowid
    return RedirectResponse(f"/erp/bills/{bill_id}?flash=Bill+B-{1000 + bill_id}+created+successfully",
                            status_code=303)


@app.get("/erp/bills/{bill_id}", response_class=HTMLResponse)
def erp_bill(request: Request, bill_id: int):
    with db.session() as c:
        found = db.rows(c, "SELECT * FROM bills WHERE id=?", bill_id)
    if not found:
        raise HTTPException(404, "Bill not found")
    return render(request, "erp_bill.html", bill=found[0])


@app.post("/erp/bills/{bill_id}/pay")
def erp_pay(bill_id: int):
    with db.session() as c:
        c.execute("UPDATE bills SET status='paid' WHERE id=?", (bill_id,))
    return RedirectResponse(f"/erp/bills/{bill_id}?flash=Bill+marked+as+paid", status_code=303)


@app.get("/erp/api/bills")
def erp_api_bills(vendor: str = "", invoice_number: str = ""):
    """Read-only JSON API (an 'integration' the agent may use via http_get)."""
    sql, args = "SELECT * FROM bills WHERE 1=1", []
    if vendor:
        sql += " AND vendor=?"
        args.append(vendor)
    if invoice_number:
        sql += " AND invoice_number=?"
        args.append(invoice_number)
    with db.session() as c:
        return {"bills": db.rows(c, sql + " ORDER BY id", *args)}


# ----------------------------------------------------------------------------- vendor portal
def _portal_ok(request: Request) -> bool:
    token = request.cookies.get("portal_session")
    if getattr(request.state, "chaos_expire_session", False) and token:
        _portal_sessions.discard(token)
    return bool(token) and token in _portal_sessions


@app.get("/portal", response_class=HTMLResponse)
def portal_home(request: Request):
    return RedirectResponse("/portal/invoices" if _portal_ok(request) else "/portal/login", status_code=302)


@app.get("/portal/login", response_class=HTMLResponse)
def portal_login(request: Request, expired: int = 0):
    msg = "Your session has expired. Please sign in again." if expired else None
    return render(request, "portal_login.html", error=msg)


@app.post("/portal/login", response_class=HTMLResponse)
def portal_login_submit(request: Request, username: str = Form(""), password: str = Form("")):
    if username.strip() != PORTAL_USER or password != PORTAL_PASSWORD:
        return render(request, "portal_login.html", error="Invalid username or password.", status_code=401)
    token = secrets.token_hex(16)
    _portal_sessions.add(token)
    resp = RedirectResponse("/portal/invoices", status_code=303)
    resp.set_cookie("portal_session", token, httponly=True)
    return resp


@app.get("/portal/invoices", response_class=HTMLResponse)
def portal_invoices(request: Request):
    if not _portal_ok(request):
        return RedirectResponse("/portal/login?expired=1", status_code=302)
    with db.session() as c:
        invoices = db.rows(c, "SELECT * FROM portal_invoices ORDER BY issue_date DESC")
    return render(request, "portal_invoices.html", invoices=invoices)


@app.get("/portal/invoices/{number}/pdf")
def portal_invoice_pdf(request: Request, number: str):
    if not _portal_ok(request):
        return RedirectResponse("/portal/login?expired=1", status_code=302)
    with db.session() as c:
        found = db.rows(c, "SELECT * FROM portal_invoices WHERE invoice_number=?", number)
    if not found:
        raise HTTPException(404, "Invoice not found")
    return FileResponse(ATTACHMENTS_DIR / found[0]["pdf"], media_type="application/pdf",
                        filename=found[0]["pdf"], content_disposition_type="inline")


@app.get("/portal/logout")
def portal_logout(request: Request):
    _portal_sessions.discard(request.cookies.get("portal_session", ""))
    return RedirectResponse("/portal/login", status_code=302)


# ----------------------------------------------------------------------------- helpdesk
@app.get("/helpdesk", response_class=HTMLResponse)
def helpdesk(request: Request, status: str = ""):
    sql, args = "SELECT * FROM tickets", []
    if status in ("open", "closed"):
        sql += " WHERE status=?"
        args.append(status)
    with db.session() as c:
        tickets = db.rows(c, sql + " ORDER BY id", *args)
    return render(request, "helpdesk_list.html", tickets=tickets, status=status)


@app.get("/helpdesk/tickets/{ticket_id}", response_class=HTMLResponse)
def helpdesk_ticket(request: Request, ticket_id: int):
    with db.session() as c:
        found = db.rows(c, "SELECT * FROM tickets WHERE id=?", ticket_id)
        notes = db.rows(c, "SELECT * FROM ticket_notes WHERE ticket_id=? ORDER BY id", ticket_id)
    if not found:
        raise HTTPException(404, "Ticket not found")
    return render(request, "helpdesk_ticket.html", ticket=found[0], notes=notes)


@app.post("/helpdesk/tickets/{ticket_id}/notes")
def helpdesk_add_note(ticket_id: int, body: str = Form("")):
    if body.strip():
        with db.session() as c:
            c.execute("INSERT INTO ticket_notes(ticket_id, body, author, created_at) VALUES(?,?,?,?)",
                      (ticket_id, body.strip(), "Atlas (AI worker)", datetime.now().isoformat(timespec="minutes")))
    return RedirectResponse(f"/helpdesk/tickets/{ticket_id}?flash=Note+added", status_code=303)


@app.post("/helpdesk/tickets/{ticket_id}/status")
def helpdesk_status(ticket_id: int, status: str = Form("closed")):
    if status not in ("open", "closed"):
        raise HTTPException(400, "bad status")
    with db.session() as c:
        c.execute("UPDATE tickets SET status=? WHERE id=?", (status, ticket_id))
    return RedirectResponse(f"/helpdesk/tickets/{ticket_id}?flash=Ticket+{status}", status_code=303)


# ----------------------------------------------------------------------------- admin (out-of-band)
@app.post("/admin/reset")
def admin_reset():
    seed.reset()
    _portal_sessions.clear()
    chaos.LOG.clear()
    return {"ok": True}


@app.get("/admin/chaos")
def admin_chaos_get():
    return {"level": chaos.level(), "log": list(chaos.LOG)[-50:]}


@app.post("/admin/chaos")
async def admin_chaos_set(request: Request):
    payload = await request.json()
    db.set_setting("chaos_level", str(float(payload.get("level", 0))))
    if "seed" in payload:
        chaos.seed(payload["seed"])
    return {"level": chaos.level()}


@app.get("/admin/state")
def admin_state():
    return db.dump_state()


@app.get("/admin/expected")
def admin_expected():
    return seed.EXPECTED


if __name__ == "__main__":
    uvicorn.run(app, host=SANDBOX_HOST, port=SANDBOX_PORT, log_level="warning")
