"""
Setup script for MetaScalp OBS Recorder
Простой скрипт для настройки - просто вставь JSON с /api/connections
"""
import json
import sys

def main():
    print("=" * 50)
    print("MetaScalp OBS Recorder - Настройка")
    print("=" * 50)
    print("\n1. Открой в браузере: http://127.0.0.1:17845/api/connections")
    print("2. Скопируй весь текст (JSON)")
    print("3. Вставь сюда и нажми Enter")
    print("(или просто нажми Enter чтобы подписаться на ВСЕ биржи)\n")
    
    json_text = input("Вставь JSON: ").strip()
    
    if not json_text:
        # Use all connections
        connections = []
        print("Будут использоваться ВСЕ активные биржи")
    else:
        try:
            data = json.loads(json_text)
            connections = data.get("connections", [])
        except json.JSONDecodeError:
            print("Ошибка: это не похоже на JSON. Запускаю с ВСЕМИ биржами...")
            connections = []
    
    # Filter active connections (State == 2)
    active = [c for c in connections if c.get("State") == 2] if connections else []
    
    if not active:
        print("\nАктивные биржи не найдены. Скрипт будет слушать все подряд.")
    
    # Create config
    config = {
        "obs": {
            "host": "127.0.0.1",
            "port": 4455,
            "password": "",
            "video_path": "e:\\video"
        },
        "exchange_ids": [c["Id"] for c in active] if active else [],
        "filename_template": "[{date}_{time}] {tickers}.mp4"
    }
    
    # Save
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    
    print(f"\n✅ Готово! Сохранено в config.json")
    print(f"   Биржи: {config['exchange_ids'] or 'ВСЕ'}")
    print(f"   Видео: {config['obs']['video_path']}")
    print("\nЗапускай: python metascalp_obs_recorder.py")

if __name__ == "__main__":
    main()