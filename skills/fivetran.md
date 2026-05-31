# Fivetran — MCP & Connector SDK Reference

## Official Documentation

- **LLM docs index**: https://fivetran.com/llms.txt
- **MCP Server (GitHub)**: https://github.com/fivetran/fivetran-mcp
- **Connector SDK docs**: https://fivetran.com/docs/connector-sdk
- **Connector SDK examples**: https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples
- **BigQuery destination setup**: https://fivetran.com/docs/destinations/bigquery/setup-guide

---

## Part 1: Fivetran MCP Server

Used by the **Agent** to trigger and monitor data pipeline syncs at runtime.

### Setup (uvx — no clone needed)

```bash
uvx --from git+https://github.com/fivetran/fivetran-mcp fivetran-mcp
```

### Key Tools (enabled by default)

| Tool | Description |
|---|---|
| `sync_connection` | Trigger a data sync for a connection |
| `get_connection_state` | Get sync state: syncing / success / failed |
| `get_connection_details` | Get last sync time, config, status |
| `list_connections` | List all connections in the account |

### Integration with Google ADK

```python
import os
from google.adk.tools.mcp_tool import MCPToolset, StdioServerParameters

fivetran_toolset = MCPToolset(
    connection_params=StdioServerParameters(
        command="uvx",
        args=["--from", "git+https://github.com/fivetran/fivetran-mcp", "fivetran-mcp"],
        env={
            "FIVETRAN_API_KEY": os.environ["FIVETRAN_API_KEY"],
            "FIVETRAN_API_SECRET": os.environ["FIVETRAN_API_SECRET"],
            "FIVETRAN_ALLOW_WRITES": "false",
        }
    ),
    tool_filter=["sync_connection", "get_connection_state", "get_connection_details"],
)
```

---

## Part 2: Fivetran Connector SDK

Used to **build custom data source connectors** — e.g. pulling from SeatGeek API or PhishHunt feed into BigQuery. This is separate from the MCP server.

Full examples: https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples

```python
# connector.py
import requests
import fivetran_connector_sdk as fdk

def schema(configuration: dict):
    return [
        fdk.Table(
            name="market_listings",
            primary_key=["listing_id"],
            columns={
                "listing_id": fdk.DataType.STRING,
                "match_id": fdk.DataType.STRING,
                "section": fdk.DataType.STRING,
                "listing_price_usd": fdk.DataType.FLOAT,
                "updated_at": fdk.DataType.UTC_DATETIME,
            }
        )
    ]

def update(configuration: dict, state: dict):
    client_id = configuration["seatgeek_client_id"]
    response = requests.get(
        "https://api.seatgeek.com/2/listings",
        params={"client_id": client_id}
    )
    for listing in response.json()["listings"]:
        yield fdk.upsert(
            table="market_listings",
            data={
                "listing_id": str(listing["id"]),
                "match_id": str(listing["event"]["id"]),
                "section": listing["section"],
                "listing_price_usd": float(listing["price"]),
                "updated_at": listing["updated_at"],
            }
        )
    yield fdk.checkpoint(state={"last_sync": "now"})

connector = fdk.Connector(update=update, schema=schema)

if __name__ == "__main__":
    connector.debug()
```

Deploy:
```bash
pip install fivetran-connector-sdk
fivetran deploy --api-key $FIVETRAN_API_KEY --api-secret $FIVETRAN_API_SECRET
```

---

## TicketGuard Pipeline Reference

| Pipeline | Connector Type | BigQuery Table |
|---|---|---|
| Pipeline_Market | Custom SDK (SeatGeek API) | `ticketguard.market_listings` |
| Pipeline_Regulation | Google Sheets connector | `ticketguard.regulation_reference` |
| Pipeline_PhishDomain | Custom SDK (PhishHunt feed) | `ticketguard.known_phishing_domains` |
