# pp-aktienfinder-import

Tool to connect the aktienfinder.net MCP server with Portfolio Performance.

The project will retrieve ETF holdings and breakdowns and create PP-compatible
taxonomy JSON files for manual import.

## Security model

- Authentication is performed with a browser-based OAuth flow.
- Passwords and refresh tokens are not saved by this project.
- Generated files contain ETF classification data only, never credentials.

## Run

python -m pp_aktienfinder_import --config example-securities.json --single-file
```powershell

The live flow opens your browser for aktienfinder.net OAuth login. This
program keeps tokens only in memory and does not save a password or refresh
token.

## Identifier rules

- ISIN entries are sent directly to the aktienfinder.net MCP server.
- NAME entries are supported only when they uniquely resolve.
- WKN entries require `portfolioXml` to point to an exported classic Portfolio
  Performance XML copy. The tool does not guess WKN-to-ISIN mappings.

## Additional safeguards

The implementation uses:

- a dry-run mode before browser authentication;
- stable keys for taxonomy categories;
- a preview mode that displays generated JSON;
- one-week MCP quota awareness through server-side errors;
- separate JSON files per ETF and taxonomy;
- no storage of account names, passwords or OAuth tokens.powershell
.\.venv\Scripts\Activate.ps1
python -m pp_aktienfinder_import --config example-securities.json --dry-run
python -m pp_aktienfinder_import --config example-securities.json --output output
```
