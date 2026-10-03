"""Default CLI delegates to V2 administration."""

def main() -> None:
    from app.v2.cli import main as platform_main
    platform_main()

if __name__ == "__main__":
    main()
