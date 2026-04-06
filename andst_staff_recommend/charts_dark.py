import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _theme_palette(theme: str = "dark"):
    theme = (theme or "dark").lower()
    if theme == "light":
        return {
            "paper": "#FFFFFF",
            "plot": "#FFFFFF",
            "grid": "#D1D5DB",
            "text": "#111827",
            "border": "#E5E7EB",
            "new": "#3B82F6",
            "exist": "#F59E0B",
            "line": "#22C55E",
            "target": "#84CC16",
            "progress": "#EF4444",
        }
    return {
        "paper": "#151A2D",
        "plot": "#151A2D",
        "grid": "#2A314D",
        "text": "#F3F4F6",
        "border": "#232845",
        "new": "#3B82F6",
        "exist": "#F59E0B",
        "line": "#22C55E",
        "target": "#84CC16",
        "progress": "#EF4444",
    }


def weekly_progress_chart(df: pd.DataFrame, category: str = "app", theme: str = "dark"):
    if df is None or df.empty:
        st.info("No chart data")
        return

    c = _theme_palette(theme)
    is_light = (theme or "dark").lower() == "light"
    axis_text = "#000000" if is_light else c["text"]
    grid_color = "#BFC5D2" if is_light else c["grid"]
    fig = go.Figure()

    bar_kwargs = dict(textfont=dict(color=axis_text))
    if category == "app":
        fig.add_bar(name="New", x=df["week_label"], y=df["new"], marker_color=c["new"], **bar_kwargs)
        fig.add_bar(name="Existing", x=df["week_label"], y=df["exist"], marker_color=c["exist"], **bar_kwargs)
        fig.add_bar(name="LINE", x=df["week_label"], y=df["line"], marker_color=c["line"], **bar_kwargs)
    else:
        fig.add_bar(name="Survey", x=df["week_label"], y=df["survey"], marker_color=c["new"], **bar_kwargs)

    fig.add_trace(
        go.Scatter(
            x=df["week_label"],
            y=[100] * len(df),
            mode="lines",
            name="Target",
            line=dict(color=c["target"], dash="dash", width=2.5),
            yaxis="y2",
            hovertemplate="%{x}<br>Target: 100%<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["week_label"],
            y=df["progress_rate"],
            mode="lines+markers+text",
            name="Progress Rate",
            line=dict(color=c["progress"], width=3),
            marker=dict(size=9, color=c["progress"]),
            text=[f"{v:.0f}%" for v in df["progress_rate"]],
            textposition="top center",
            textfont=dict(color=axis_text, size=14),
            cliponaxis=False,
            yaxis="y2",
            hovertemplate="%{x}<br>Progress Rate: %{y:.1f}%<extra></extra>",
        )
    )

    fig.update_layout(
        barmode="stack",
        bargap=0.55,
        bargroupgap=0.08,
        height=440,
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor=c["paper"],
        plot_bgcolor=c["plot"],
        font=dict(color=axis_text),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color=axis_text),
        ),
        hovermode="x unified",
        xaxis=dict(
            title="Week",
            gridcolor=grid_color,
            zeroline=False,
            title_font=dict(color=axis_text),
            tickfont=dict(color=axis_text),
            linecolor=axis_text,
        ),
        yaxis=dict(
            title="Count",
            gridcolor=grid_color,
            zeroline=False,
            title_font=dict(color=axis_text),
            tickfont=dict(color=axis_text),
        ),
        yaxis2=dict(
            title="Progress Rate (%)",
            overlaying="y",
            side="right",
            showgrid=False,
            rangemode="tozero",
            title_font=dict(color=axis_text),
            tickfont=dict(color=axis_text),
        ),
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})
