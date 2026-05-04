# app.py — Indiana Medicaid FWA Analytics Dashboard
# H517 Final Project | Indiana FSSA Provider Claims 2012–2017
# Deployed on Render via GitHub

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import plotly.express as px
from dash import Dash, html, dcc, Input, Output, dash_table, ctx
import dash_bootstrap_components as dbc

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA LOADING & CLEANING
# ─────────────────────────────────────────────────────────────────────────────

DATA_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTux2p0df-i_wSq4UTqxVmoQ0dcRGuSAqwMUq-EtHTQRjlKopAWcu2Of0K9BVLHpI00atdAScFdmZUm/pub?output=csv'

NUMERIC_COLS = [
    "total_number_of_recipients",
    "total_number_of_claims",
    "total_dollar_amount_of_claims",
    "recipients_average_traveled_distance_miles",
    "provider_geocode_latitude",
    "Provider_geocode_longitude",
    "Year",
]


def load_data() -> pd.DataFrame:
    df_raw = pd.read_csv(DATA_URL, dtype=str)
    df = df_raw.apply(lambda col: col.str.strip() if col.dtype == "object" else col)
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # Indiana records only
    df_in = df[df["Provider_address_state"] == "IN"].copy()
    df_in["Year"] = df_in["Year"].astype("Int64")
    return df_in


print("Loading Indiana Medicaid data…")
DF = load_data()
print(f"  {len(DF):,} records loaded.")

# Derived constants for filter dropdowns
ALL_YEARS = sorted(DF["Year"].dropna().unique().tolist())
ALL_TYPES = sorted(DF["provider_type"].dropna().unique().tolist())
ALL_CATS  = sorted(DF["Category_of_services"].dropna().unique().tolist())
YEAR_MIN, YEAR_MAX = int(min(ALL_YEARS)), int(max(ALL_YEARS))

# Colorblind-safe qualitative palette (Plotly Safe palette)
SAFE_COLORS = px.colors.qualitative.Safe

# Indiana bounding box for valid coordinates
LAT_MIN, LAT_MAX = 37.77, 41.76
LON_MIN, LON_MAX = -88.10, -84.78


# ─────────────────────────────────────────────────────────────────────────────
# 2. APP INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    title="Indiana Medicaid FWA Analytics",
    suppress_callback_exceptions=True,
)
server = app.server  # Expose Flask server for gunicorn / Render


# ─────────────────────────────────────────────────────────────────────────────
# 3. LAYOUT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def insight_text(text: str):
    """Small muted callout shown beneath each chart title."""
    return html.P(text, className="text-muted small fst-italic mb-2")


def empty_fig(message="No data for the current filter selection."):
    """Return a blank figure with a centered message."""
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_annotation(
        text=message, x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False, font=dict(size=14, color="#6c757d"),
    )
    fig.update_layout(
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def sidebar():
    return dbc.Card(
        [
            dbc.CardHeader(html.H6("Filters", className="mb-0 fw-bold text-primary")),
            dbc.CardBody(
                [
                    html.Label("Year Range", className="fw-semibold small text-secondary"),
                    dcc.RangeSlider(
                        id="year-slider",
                        min=YEAR_MIN, max=YEAR_MAX, step=1,
                        value=[YEAR_MIN, YEAR_MAX],
                        marks={y: {"label": str(y), "style": {"fontSize": "11px"}}
                               for y in ALL_YEARS},
                        tooltip={"placement": "bottom", "always_visible": False},
                        className="mb-4",
                    ),
                    html.Hr(className="my-2"),
                    html.Label("Provider Type", className="fw-semibold small text-secondary"),
                    dcc.Dropdown(
                        id="type-dropdown",
                        options=[{"label": t, "value": t} for t in ALL_TYPES],
                        multi=True,
                        placeholder="All types…",
                        className="mb-3",
                    ),
                    html.Hr(className="my-2"),
                    html.Label("Service Category", className="fw-semibold small text-secondary"),
                    dcc.Dropdown(
                        id="cat-dropdown",
                        options=[{"label": c, "value": c} for c in ALL_CATS],
                        multi=True,
                        placeholder="All categories…",
                        className="mb-3",
                    ),
                    html.Hr(className="my-2"),
                    dbc.Button(
                        "Reset Filters", id="reset-btn",
                        color="secondary", outline=True, size="sm", className="w-100",
                    ),
                    html.Hr(className="my-3"),
                    # Summary KPI cards
                    html.Div(id="kpi-cards"),
                ]
            ),
        ],
        className="sticky-top shadow-sm",
        style={"top": "80px"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. TAB DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

tab_geo = dbc.Tab(
    label="Geographic Overview",
    tab_id="tab-geo",
    children=[
        dbc.Row(dbc.Col([
            html.H5("Provider Map — Claim Volume & Total Dollars", className="mt-3 mb-0"),
            insight_text(
                "Bubble size = total claims billed; color = total dollars. "
                "Isolated high-dollar bubbles far from urban centers may warrant closer review."
            ),
            dcc.Loading(dcc.Graph(id="map-chart", style={"height": "500px"})),
        ])),
        dbc.Row(dbc.Col([
            html.H5("Year-over-Year Claim Volume by Provider Type", className="mt-4 mb-0"),
            insight_text(
                "Showing the top 8 provider types by total claims for the selected filters. "
                "A sharp spike in one type relative to peers can signal a billing anomaly or new large entrant."
            ),
            dcc.Loading(dcc.Graph(id="trend-chart", style={"height": "380px"})),
        ])),
    ],
)

tab_spend = dbc.Tab(
    label="Spending Analysis",
    tab_id="tab-spend",
    children=[
        dbc.Row(dbc.Col([
            html.H5("Total Claim Dollars by Service Category", className="mt-3 mb-0"),
            insight_text(
                "Hover to see average cost per claim. "
                "A high average cost relative to peers may indicate pricing anomalies."
            ),
            dcc.Loading(dcc.Graph(id="bar-chart", style={"height": "420px"})),
        ])),
        dbc.Row(dbc.Col([
            html.H5("Spending by Provider Type → Service Category", className="mt-4 mb-0"),
            insight_text(
                "Click any provider type to zoom in. "
                "Types concentrated in a single high-reimbursement category may indicate upcoding."
            ),
            dcc.Loading(dcc.Graph(id="treemap-chart", style={"height": "500px"})),
        ])),
    ],
)

tab_fwa = dbc.Tab(
    label="FWA Signal Detection",
    tab_id="tab-fwa",
    children=[
        dbc.Row(dbc.Col([
            html.H5("Claims per Recipient vs. Recipient Volume", className="mt-3 mb-0"),
            insight_text(
                "Providers above the red dashed line (95th percentile) with large bubbles "
                "(high total dollars) are flagged as potential FWA signals. "
                "Top flagged providers are labeled — these are patterns, not confirmed fraud."
            ),
            dcc.Loading(dcc.Graph(id="fwa-chart", style={"height": "520px"})),
        ])),
        dbc.Row(dbc.Col([
            html.H5("Flagged Providers", className="mt-4 mb-0 text-danger"),
            insight_text(
                "Criteria: top 5% claims/recipient AND top 25% total dollars. "
                "Sorted by claims per recipient descending. Click a column header to re-sort."
            ),
            html.Div(id="flagged-table"),
        ])),
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
# 5. FULL APP LAYOUT
# ─────────────────────────────────────────────────────────────────────────────

app.layout = dbc.Container(
    [
        # ── Header bar ────────────────────────────────────────────────────────
        dbc.Navbar(
            dbc.Container(
                html.Div(
                    [
                        html.H4(
                            "Indiana Medicaid FWA Analytics",
                            className="mb-0 text-white fw-bold",
                        ),
                        html.Small(
                            "2012–2017 · Indiana FSSA Provider Claims · "
                            "Statistical patterns, not confirmed fraud",
                            className="text-white-50",
                        ),
                    ]
                ),
                fluid=True,
            ),
            color="primary",
            dark=True,
            className="mb-4 px-3",
        ),

        # ── Sidebar + tabbed main panel ────────────────────────────────────
        dbc.Row(
            [
                dbc.Col(sidebar(), width=3),
                dbc.Col(
                    dbc.Tabs(
                        [tab_geo, tab_spend, tab_fwa],
                        id="main-tabs",
                        active_tab="tab-geo",
                    ),
                    width=9,
                ),
            ],
            className="g-3",
        ),

        # ── Footer ────────────────────────────────────────────────────────────
        html.Hr(className="mt-5"),
        html.P(
            [
                "Data: ",
                html.A(
                    "Indiana FSSA via Indiana Data Hub",
                    href="https://hub.mph.in.gov/dataset/medicaid-claims/resource/d0b90bc6-8f6e-4676-a682-bbf1ac202790",
                    target="_blank",
                ),
                " · Aggregated provider-level claims · "
                "Anomalies reflect statistical patterns, not confirmed FWA incidents.",
            ],
            className="text-muted small text-center mb-3",
        ),
    ],
    fluid=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# 6. HELPER: APPLY SHARED FILTERS
# ─────────────────────────────────────────────────────────────────────────────

def apply_filters(
    year_range: list,
    types: list | None,
    cats: list | None,
) -> pd.DataFrame:
    mask = (DF["Year"] >= year_range[0]) & (DF["Year"] <= year_range[1])
    if types:
        mask &= DF["provider_type"].isin(types)
    if cats:
        mask &= DF["Category_of_services"].isin(cats)
    return DF[mask].copy()


# ─────────────────────────────────────────────────────────────────────────────
# 7. CALLBACK: RESET FILTERS
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output("year-slider", "value"),
    Output("type-dropdown", "value"),
    Output("cat-dropdown", "value"),
    Input("reset-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_):
    return [YEAR_MIN, YEAR_MAX], None, None


# ─────────────────────────────────────────────────────────────────────────────
# 8. CALLBACK: KPI SUMMARY CARDS (sidebar)
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output("kpi-cards", "children"),
    Input("year-slider", "value"),
    Input("type-dropdown", "value"),
    Input("cat-dropdown", "value"),
)
def update_kpis(year_range, types, cats):
    dff = apply_filters(year_range, types, cats)
    if dff.empty:
        return html.P("No data.", className="text-muted small")

    total_dollars = dff["total_dollar_amount_of_claims"].sum()
    total_claims  = dff["total_number_of_claims"].sum()
    n_providers   = dff["Provider_NPI"].nunique()

    def kpi(label, value):
        return dbc.Card(
            dbc.CardBody([
                html.P(label, className="text-muted small mb-0"),
                html.H6(value, className="fw-bold mb-0"),
            ]),
            className="mb-2 shadow-sm border-0 bg-light",
        )

    return [
        kpi("Total Dollars", f"${total_dollars / 1e9:.2f}B"),
        kpi("Total Claims", f"{total_claims / 1e6:.1f}M"),
        kpi("Unique Providers", f"{n_providers:,}"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 9. CALLBACK: ALL CHARTS (shared filter inputs → 6 outputs)
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output("map-chart",     "figure"),
    Output("trend-chart",   "figure"),
    Output("bar-chart",     "figure"),
    Output("treemap-chart", "figure"),
    Output("fwa-chart",     "figure"),
    Output("flagged-table", "children"),
    Input("year-slider",    "value"),
    Input("type-dropdown",  "value"),
    Input("cat-dropdown",   "value"),
)
def update_charts(year_range, types, cats):
    dff = apply_filters(year_range, types, cats)

    if dff.empty:
        ef = empty_fig()
        return ef, ef, ef, ef, ef, html.P("No data for the current filters.", className="text-muted")

    # ── MAP ─────────────────────────────────────────────────────────────────
    geo_df = (
        dff
        .dropna(subset=["provider_geocode_latitude", "Provider_geocode_longitude"])
        .query(
            f"{LAT_MIN} <= provider_geocode_latitude <= {LAT_MAX} and "
            f"{LON_MIN} <= Provider_geocode_longitude <= {LON_MAX}"
        )
        .groupby(
            ["Provider_NPI", "provider_name", "provider_type",
             "provider_geocode_latitude", "Provider_geocode_longitude"],
            as_index=False,
        )
        .agg(
            total_claims     =("total_number_of_claims",           "sum"),
            total_dollars    =("total_dollar_amount_of_claims",    "sum"),
            total_recipients =("total_number_of_recipients",       "sum"),
        )
        .query("total_claims > 0 and total_dollars > 0")
    )

    if geo_df.empty:
        fig_map = empty_fig("No mappable providers for this filter selection.")
    else:
        fig_map = px.scatter_mapbox(
            geo_df,
            lat="provider_geocode_latitude",
            lon="Provider_geocode_longitude",
            color="total_dollars",
            size="total_claims",
            hover_name="provider_name",
            hover_data={
                "provider_type":              True,
                "total_claims":               ":,",
                "total_dollars":              ":,.0f",
                "total_recipients":           ":,",
                "provider_geocode_latitude":  False,
                "Provider_geocode_longitude": False,
            },
            color_continuous_scale="YlOrRd",
            size_max=30,
            zoom=6,
            center={"lat": 39.8, "lon": -86.1},
            mapbox_style="carto-positron",
            labels={
                "total_dollars":    "Total Dollars ($)",
                "total_claims":     "Total Claims",
                "provider_type":    "Provider Type",
                "total_recipients": "Recipients Served",
            },
        )
        fig_map.update_layout(
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            coloraxis_colorbar=dict(title="Total $", tickformat="$,.0s"),
        )

    # ── TREND ───────────────────────────────────────────────────────────────
    top_types = (
        dff.groupby("provider_type")["total_number_of_claims"]
        .sum().nlargest(8).index.tolist()
    )
    trend_df = (
        dff[dff["provider_type"].isin(top_types)]
        .groupby(["Year", "provider_type"], as_index=False)
        .agg(total_claims=("total_number_of_claims", "sum"))
    )
    trend_df["Year"] = trend_df["Year"].astype(int)

    if trend_df.empty:
        fig_trend = empty_fig()
    else:
        fig_trend = px.line(
            trend_df, x="Year", y="total_claims", color="provider_type",
            markers=True,
            color_discrete_sequence=SAFE_COLORS,
            labels={
                "total_claims":   "Total Claims",
                "provider_type":  "Provider Type",
                "Year":           "Year",
            },
        )
        fig_trend.update_layout(
            hovermode="x unified",
            xaxis=dict(tickmode="linear", dtick=1),
            yaxis=dict(tickformat=","),
            legend=dict(
                title="Provider Type", orientation="h",
                yanchor="bottom", y=1.02, xanchor="right", x=1,
            ),
            margin={"t": 60},
        )

    # ── CATEGORY BAR ────────────────────────────────────────────────────────
    cat_df = (
        dff.groupby("Category_of_services", as_index=False)
        .agg(
            total_dollars    =("total_dollar_amount_of_claims",  "sum"),
            total_claims     =("total_number_of_claims",         "sum"),
            total_recipients =("total_number_of_recipients",     "sum"),
        )
        .sort_values("total_dollars")
    )
    cat_df["avg_cost_per_claim"] = (
        cat_df["total_dollars"] / cat_df["total_claims"].replace(0, pd.NA)
    ).round(2)

    if cat_df.empty:
        fig_bar = empty_fig()
    else:
        fig_bar = px.bar(
            cat_df, x="total_dollars", y="Category_of_services",
            orientation="h",
            color="total_dollars",
            color_continuous_scale="Blues",
            hover_data={
                "total_claims":        ":,",
                "total_recipients":    ":,",
                "avg_cost_per_claim":  ":,.2f",
                "total_dollars":       False,
            },
            labels={
                "total_dollars":       "Total Claim Dollars ($)",
                "Category_of_services":"Service Category",
                "total_claims":        "Total Claims",
                "total_recipients":    "Total Recipients",
                "avg_cost_per_claim":  "Avg Cost / Claim ($)",
            },
        )
        fig_bar.update_layout(
            xaxis=dict(tickformat="$,.2s"),
            coloraxis_showscale=False,
            margin={"t": 20},
        )

    # ── TREEMAP ─────────────────────────────────────────────────────────────
    tree_df = (
        dff.groupby(["provider_type", "Category_of_services"], as_index=False)
        .agg(total_dollars=("total_dollar_amount_of_claims", "sum"))
        .query("total_dollars > 0")
    )

    if tree_df.empty:
        fig_tree = empty_fig()
    else:
        fig_tree = px.treemap(
            tree_df,
            path=[px.Constant("Indiana Medicaid"), "provider_type", "Category_of_services"],
            values="total_dollars",
            color="total_dollars",
            color_continuous_scale="Teal",
            labels={"total_dollars": "Total Claim Dollars ($)"},
        )
        fig_tree.update_traces(
            texttemplate="%{label}<br>$%{value:,.0f}",
            hovertemplate="<b>%{label}</b><br>Total: $%{value:,.0f}<extra></extra>",
        )
        fig_tree.update_layout(
            coloraxis_colorbar=dict(title="Total $", tickformat="$,.0s"),
            margin={"t": 20},
        )

    # ── FWA SCATTER ─────────────────────────────────────────────────────────
    prov_df = (
        dff.groupby(["Provider_NPI", "provider_name", "provider_type"], as_index=False)
        .agg(
            total_claims     =("total_number_of_claims",                      "sum"),
            total_recipients =("total_number_of_recipients",                  "sum"),
            total_dollars    =("total_dollar_amount_of_claims",               "sum"),
            avg_travel_mi    =("recipients_average_travelled_distance_miles",  "mean"),
        )
        .query("total_recipients > 0 and total_dollars > 0")
    )
    prov_df["claims_per_recipient"] = (
        prov_df["total_claims"] / prov_df["total_recipients"]
    )

    threshold_cpr     = prov_df["claims_per_recipient"].quantile(0.95)
    threshold_dollars = prov_df["total_dollars"].quantile(0.75)
    prov_df["flagged"] = (
        (prov_df["claims_per_recipient"] > threshold_cpr) &
        (prov_df["total_dollars"] > threshold_dollars)
    )

    if prov_df.empty:
        fig_fwa = empty_fig()
        flagged_table_el = html.P("No data.", className="text-muted")
    else:
        fig_fwa = px.scatter(
            prov_df,
            x="total_recipients", y="claims_per_recipient",
            color="provider_type",
            size="total_dollars",
            size_max=25,
            hover_name="provider_name",
            hover_data={
                "total_claims":     ":,",
                "total_recipients": ":,",
                "total_dollars":    ":,.0f",
                "avg_travel_mi":    ":.1f",
                "provider_type":    False,
                "flagged":          False,
            },
            log_x=True,
            color_discrete_sequence=SAFE_COLORS,
            labels={
                "total_recipients":      "Total Recipients Served (log scale)",
                "claims_per_recipient":  "Claims per Recipient",
                "total_dollars":         "Total Dollars ($)",
                "avg_travel_mi":         "Avg Travel Distance (mi)",
                "provider_type":         "Provider Type",
            },
        )

        # 95th-percentile reference line
        fig_fwa.add_hline(
            y=threshold_cpr,
            line_dash="dash",
            line_color="red",
            annotation_text=f"95th percentile — {threshold_cpr:.1f} claims/recipient",
            annotation_position="top left",
            annotation_font=dict(color="red", size=11),
        )

        # Label top 5 flagged providers
        top5_flagged = (
            prov_df[prov_df["flagged"]]
            .nlargest(5, "claims_per_recipient")
        )
        for _, row in top5_flagged.iterrows():
            label = row["provider_name"].title()
            label = label[:32] + "…" if len(label) > 32 else label
            fig_fwa.add_annotation(
                x=row["total_recipients"],
                y=row["claims_per_recipient"],
                text=label,
                showarrow=True, arrowhead=2, arrowsize=0.8,
                ax=45, ay=-35,
                font=dict(size=9, color="#c0392b"),
                xref="x", yref="y",
            )

        fig_fwa.update_layout(
            legend=dict(
                title="Provider Type", orientation="h",
                yanchor="bottom", y=1.02, xanchor="right", x=1,
            ),
            margin={"t": 60},
        )

        # ── FLAGGED TABLE ──────────────────────────────────────────────────
        flagged_df = (
            prov_df[prov_df["flagged"]]
            .sort_values("claims_per_recipient", ascending=False)
            [["provider_name", "provider_type", "total_claims",
              "total_recipients", "claims_per_recipient", "total_dollars"]]
            .copy()
        )
        flagged_df.columns = [
            "Provider", "Type", "Total Claims",
            "Total Recipients", "Claims / Recipient", "Total Dollars ($)",
        ]
        flagged_df["Claims / Recipient"] = flagged_df["Claims / Recipient"].round(1)
        flagged_df["Total Dollars ($)"]  = flagged_df["Total Dollars ($)"].apply(lambda x: f"${x:,.0f}")
        flagged_df["Total Claims"]       = flagged_df["Total Claims"].apply(lambda x: f"{int(x):,}")
        flagged_df["Total Recipients"]   = flagged_df["Total Recipients"].apply(lambda x: f"{int(x):,}")

        flagged_table_el = dash_table.DataTable(
            data=flagged_df.head(30).to_dict("records"),
            columns=[{"name": c, "id": c} for c in flagged_df.columns],
            style_table={"overflowX": "auto"},
            style_cell={
                "fontSize": 12, "padding": "6px 10px",
                "textAlign": "left", "fontFamily": "sans-serif",
            },
            style_header={
                "backgroundColor": "#c0392b",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": 12,
            },
            style_data_conditional=[
                {
                    "if": {"row_index": "odd"},
                    "backgroundColor": "#fdf2f2",
                }
            ],
            page_size=15,
            sort_action="native",
            filter_action="native",
        )

    return fig_map, fig_trend, fig_bar, fig_tree, fig_fwa, flagged_table_el


# ─────────────────────────────────────────────────────────────────────────────
# 10. ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=8050)
