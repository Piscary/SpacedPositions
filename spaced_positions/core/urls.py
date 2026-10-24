from django.urls import path

from . import chess_views, engine_local, settings_view, views

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
    path("settings/rows/", settings_view.settings_rows, name="settings_rows"),
    path("settings/keymap/", settings_view.keymap_rows, name="keymap_rows"),
    path("settings/export/", settings_view.export_settings, name="settings_export"),
    path("settings/import/", settings_view.import_settings, name="settings_import"),
    path("engine/local/", engine_local.local, name="engine_local"),
    path("pieces/user.css", settings_view.user_pieces_css, name="user_pieces_css"),
    path("pieces/<slug:name>/<str:code>.svg", settings_view.user_piece, name="user_piece"),
    path("<str:mode>/", views.mode_page, name="mode"),
]
