# pp-aktienfinder-import

`pp-aktienfinder-import` reads selected ETF data from the official
aktienfinder.net MCP server and creates taxonomies that can be imported into
Portfolio Performance (PP).

The tool is an external converter. It does not modify Portfolio Performance
and does not change a PP database automatically. The resulting JSON is first
shown in a preview or saved locally, and only an explicit PP import changes the
open PP database.

## What the project creates

Depending on the configuration, the tool creates PP taxonomy JSON for:

- **Country**: country weights of the analyzed ETF holdings
- **Region**: regional weights
- **Sector**: supersector weights
- **Industry**: industry weights, optional
- **Holding**: the largest ETF holdings and their weights

The top-holdings setting defaults to `10`.

## Requirements

- Windows
- Python 3.13
- An internet connection
- A premium aktienfinder.net account with MCP access
- Portfolio Performance, for importing and reviewing the JSON later

The repository contains a Python virtual environment under `.venv` after
installation.

## Installation

From the repository directory:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

The package entry point can then also be invoked as:

```powershell
pp-af-import --help
```

## Quick start

Validate the example configuration without opening the browser:

```powershell
python -m pp_aktienfinder_import --config example-securities.json --dry-run
```

Create one combined JSON file for the PP multi-taxonomy importer:

```powershell
python -m pp_aktienfinder_import --config example-securities.json --single-file --output output
```

This creates:

```text
output\pp-taxonomies.json
```

Create separate JSON files instead:

```powershell
python -m pp_aktienfinder_import --config example-securities.json --output output
```

Possible separate files include:

```text
output\country-<ISIN>.json
output\region-<ISIN>.json
output\sector-<ISIN>.json
output\industry-<ISIN>.json
output\holding-<ISIN>.json
```

## Command-line parameters

Run `python -m pp_aktienfinder_import --help` to show the same options.

| Parameter | Default | Description |
|---|---|---|
| `--config <PATH>` | `example-securities.json` | Loads the JSON parameter file |
| `--portfolio-xml <PATH>` | unset | Classic PP XML copy used only to resolve WKN values to ISIN values |
| `--output <DIRECTORY>` | `output` | Destination directory for generated JSON |
| `--dry-run` | disabled | Validates identifiers and configuration, prints the plan and performs no OAuth or MCP calls |
| `--preview` | disabled | Prints generated taxonomy JSON to the console instead of writing output files |
| `--single-file` | disabled | Writes all taxonomies into one `pp-taxonomies.json` array |

`--preview` and `--single-file` are intended as alternative output modes.
`--dry-run` can be combined with the other options, but it stops before
authentication and export.

The package entry point supports the same parameters:

```powershell
pp-af-import --config example-securities.json --single-file --output output
```

## Parameter file

The parameter file is a JSON object.

```json
{
  "securities": [
    {
      "identifier": "IE00B4K48X80",
      "identifierType": "ISIN"
    }
  ],
  "portfolioXml": null,
  "taxonomy": {
    "country": true,
    "region": true,
    "sector": true,
    "industry": false,
    "holdings": true,
    "topHoldings": 10
  },
  "options": {
    "dryRun": false,
    "previewOnly": false
  }
}
```

### `securities`

A non-empty array of securities to process.

Each item supports:

| Field | Required | Allowed values | Description |
|---|---|---|---|
| `identifier` | yes | non-empty string | ISIN, WKN or name |
| `identifierType` | yes | `ISIN`, `WKN`, `NAME` | Identifies how the value is interpreted |

ISIN values are sent directly to aktienfinder.net.

NAME values are passed only if they can be resolved uniquely by the MCP server.
An ambiguous name returns candidates and requires an ISIN.

WKN values need `portfolioXml`. The XML is searched for matching `wkn` and
`isin` attributes. The project does not query a third-party WKN database and
does not guess mappings.

### `portfolioXml`

Optional path to an unencrypted classic Portfolio Performance XML copy.

Example:

```json
"portfolioXml": "C:/Users/name/Documents/Portfolio.xml"
```

It is needed only for `WKN` identifiers. `ISIN` and `NAME` entries do not need
it.

On the command line, `--portfolio-xml` overrides the `portfolioXml` value in
the parameter file.

### `taxonomy`

Controls which MCP breakdown dimensions and holdings are requested.

| Field | Type | Default | Description |
|---|---:|---:|---|
| `country` | boolean | `true` | Requests country weights |
| `region` | boolean | `true` | Requests region weights |
| `sector` | boolean | `true` | Requests supersector weights |
| `industry` | boolean | `false` | Requests the finer industry breakdown |
| `holdings` | boolean | `true` | Requests ETF holdings |
| `topHoldings` | integer | `10` | Number of largest holdings retained, range `1` to `100` |

Country, region and sector weights refer to the analyzed stocks.
`AnalyzedStocksDensityPercent` indicates how much of the ETF was covered;
the MCP result may therefore differ from a complete 100 percent fund view.

### `options`

The current CLI uses command-line switches for live behavior.
The `options` object is reserved for configuration metadata and is not used to
override authentication or file output.

## Authentication

The project uses OAuth 2.1 with PKCE:

1. It opens the aktienfinder.net login page in the default browser.
2. The user signs in to the own aktienfinder.net account.
3. The browser redirects to the local callback at
   `http://127.0.0.1:8765/callback`.
4. The callback listener captures only the short-lived authorization code.
5. MCP bearer and refresh values remain in memory for the running process.

The project does not store:

- username or password
- refresh token
- access token
- browser cookies

Restarting the process starts a new browser login.

The MCP server is called at:

```text
https://aktienfinder.net/mcp
```

The server requires a premium membership and applies its own rate limits and
weekly tool quota.

## MCP calls

For each ETF the tool can call:

- `get_etf_breakdown` for Country, Region, Sector or Industry
- `get_etf_holdings` for holdings and weights

The default example requests:

- all four ETFs through ISIN
- Country, Region and Sector
- no Industry breakdown
- Holdings with the top `10` entries

`get_etf_holdings` is paged. The tool follows `NextOffset` until `Truncated`
is false.

## Generated JSON format

Each taxonomy document contains:

- `name`: taxonomy name
- `categories`: category names and stable keys
- `instruments`: security identifiers and category assignments

Example:

```json
{
  "name": "Country",
  "categories": [
    {
      "name": "USA",
      "key": "country-usa"
    }
  ],
  "instruments": [
    {
      "identifiers": {
        "isin": "IE00B4X9L533"
      },
      "categories": [
        {
          "key": "country-usa",
          "weight": 70.66
        }
      ]
    }
  ]
}
```

Category keys are generated from the taxonomy dimension and category name.
They are intentionally stable, so later imports can update existing categories
instead of always creating duplicates.

## Separate and combined output

Without an output mode:

```powershell
python -m pp_aktienfinder_import --config example-securities.json --output output
```

the tool creates one file per ETF and taxonomy.

With:

```powershell
python -m pp_aktienfinder_import --config example-securities.json --single-file --output output
```

the tool combines all documents into:

```text
output\pp-taxonomies.json
```

The combined file is a JSON array. It contains one object for each generated
taxonomy and is accepted by the Portfolio Performance multi-taxonomy import
wizard.

For a console-only preview:

```powershell
python -m pp_aktienfinder_import --config example-securities.json --preview
```

No JSON files are written in preview mode.

## Import into Portfolio Performance

1. Create a backup copy of the Portfolio Performance file.
2. Run the project with `--single-file`.
3. Open Portfolio Performance.
4. Start **Taxonomies → Import** or the corresponding taxonomy import command.
5. Select `pp-taxonomies.json`.
6. Choose `NEW` or `UPDATE` for each taxonomy.
7. Review the additions and changed assignments.
8. Finish the import and save the PP file.

It is safer to keep replace/pruning options disabled during the first test,
unless obsolete categories and assignments should explicitly be removed.

The top-holdings taxonomy can be imported as a normal PP taxonomy:

- holding name = stock name
- holding weight = ETF weight
- stable key = `holding-<ISIN-or-name>`

## Logging

The live command writes communication metadata to:

```text
aktienfinder-live.log
```

The log contains MCP start, initialization, tool request and tool response
events. It must not contain credentials or OAuth tokens.

The current log configuration excludes sensitive keys such as:

- `authorization`
- `access_token`
- `refresh_token`
- `token`
- `password`
- `secret`
- `cookie`
- `set-cookie`

`*.log` is excluded from Git.

## Security recommendations

- Do not commit parameter files containing private information.
- Keep `example-securities.json` as the public example.
- Keep `output/` and `*.log` local.
- Use a backup copy of the PP XML and PP database.
- Review an MCP response before selecting PP `UPDATE`.
- Avoid the PP replace/prune option until classifications have been compared.
- Review aktienfinder.net terms and MCP quota limits before larger runs.

## Troubleshooting

### The browser login opens but MCP authorization fails

Check that:

- the aktienfinder.net membership is active;
- the account has MCP access;
- the browser callback can reach `127.0.0.1:8765`;
- no other process uses port `8765`;
- the MCP server is reachable.

### A `WKN` cannot be resolved

Provide `--portfolio-xml` or set `portfolioXml` in the parameter file, and use
the unencrypted classic PP XML format. Alternatively, replace the WKN with an
ISIN.

### An ISIN is reported as not found

The ETF or instrument may not be covered by aktienfinder.net. The MCP response
contains an `Errors` entry with the provider's reason.

### The result is ambiguous

Use the ISIN returned by the MCP `Candidates` result instead of a name.

### MCP quota or rate-limit errors occur

Wait until the MCP server reports the next available time. The project does
not bypass server quotas. Multiple ETFs should be queried in blocks rather
than repeated individually.

## Testing

Run local tests from the repository:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src
python -m pp_aktienfinder_import --config example-securities.json --dry-run
```
