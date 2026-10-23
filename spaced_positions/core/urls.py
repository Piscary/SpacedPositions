from django.urls import path

from . import chess_views, views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("m/<str:mode>/", views.workspace, name="workspace"),
    path("m/<str:mode>/default", views.default_layout, name="default_layout"),
    path("v/<str:view>/", views.view_fragment, name="view"),
    path("state/<str:mode>/", views.save_state, name="save_state"),
    path("layouts/", views.named_layouts, name="layouts"),
    path("cmd/<str:cid>/", views.run_command, name="command"),
    path("chess/fen/", chess_views.fen_check, name="fen_check"),
    path("chess/paste/", chess_views.paste, name="paste"),
    path("svg/board/", chess_views.board_svg, name="board_svg"),
    path("<str:mode>/", views.mode_page, name="mode"),
]
