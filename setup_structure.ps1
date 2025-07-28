
# （以下はフォルダと空ファイルを大量に作る処理。一度で終わります）
'' | Set-Content README.md
'' | Set-Content pyproject.toml
'' | Set-Content .env.example
New-Item docs,configs,scripts,gap_bot,gap_bot\ml,gap_bot\utils,sdk,tests -ItemType Directory | Out-Null
'' | Set-Content docs\strategy_v2.md
'' | Set-Content configs\config.yaml
'' | Set-Content configs\dashboard.yaml
@('run_screen.py','run_entry.py','run_live.py','run_close.py','retrain_ml.py','weekly_report.py') |
  ForEach-Object { '' | Set-Content ("scripts\$_") }
@('filters.py','position_sizer.py','order_manager.py','slippage_monitor.py') |
  ForEach-Object { '' | Set-Content ("gap_bot\$_") }
'' | Set-Content gap_bot\__init__.py
'' | Set-Content gap_bot\ml\__init__.py
'' | Set-Content gap_bot\ml\model.py
'' | Set-Content gap_bot\utils\__init__.py
'' | Set-Content sdk\__init__.py
'' | Set-Content sdk\webull_sdk_wrapper.py
Write-Host "✅ ディレクトリ構造とプレースホルダーが作成されました。"
