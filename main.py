def main() -> None:
    from taxi_bot.app import build_app

    app = build_app()
    app.run_polling()


if __name__ == "__main__":
    print("Starting Vinayaga Taxi bot (polling mode)...")
    main()
