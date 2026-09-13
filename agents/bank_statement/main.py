import argparse
from pathlib import Path

from bank_statement_agent import run_statement_files, run_transactions_file


def main():
    parser = argparse.ArgumentParser(
        description="Run the TraceChain bank statement agent on a transactions CSV."
    )
    parser.add_argument(
        "input_path",
        help="Combined transactions CSV or directory containing exactly 10 statement CSVs",
    )
    parser.add_argument(
        "--output",
        default="data/processed/bank_statement_agent_output.json",
        help="JSON output path",
    )
    args = parser.parse_args()
    input_path = Path(args.input_path)
    if input_path.is_dir():
        statement_files = sorted(input_path.glob("*.csv"))
        result = run_statement_files(
            statement_files,
            args.output,
            expected_account_ids=[str(100001 + index) for index in range(10)],
        )
    else:
        result = run_transactions_file(input_path, args.output)
    print(f"Processed {len(result['records'])} account(s).")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
