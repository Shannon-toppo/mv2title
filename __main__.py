try:
	from .cli import main
except ImportError:
	from cli import main  # type: ignore

if __name__ == "__main__":
	raise SystemExit(main())
