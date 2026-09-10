import chromadb
from pathlib import Path

# ---------------------------------------------------------
# Find the project folder automatically
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

# Policy folder
policy_folder = BASE_DIR / "policies"

# ChromaDB storage folder
chroma_folder = BASE_DIR / "chroma_db"

print("Project folder:", BASE_DIR)
print("Policy folder:", policy_folder)

# ---------------------------------------------------------
# Check whether policy folder exists
# ---------------------------------------------------------

if not policy_folder.exists():
    print("ERROR: policies folder not found!")
    exit()

# Find Markdown files
policy_files = list(policy_folder.glob("*.md"))

print("Policy files found:", len(policy_files))

for file in policy_files:
    print("  -", file.name)

# ---------------------------------------------------------
# Create ChromaDB
# ---------------------------------------------------------

client = chromadb.PersistentClient(
    path=str(chroma_folder)
)

collection = client.get_or_create_collection(
    name="payslip_policies"
)

# ---------------------------------------------------------
# Load policy documents
# ---------------------------------------------------------

for file in policy_files:

    text = file.read_text(
        encoding="utf-8"
    )

    collection.upsert(
        documents=[text],
        ids=[file.stem],
        metadatas=[
            {
                "source": file.name
            }
        ]
    )

    print("Added:", file.name)

# ---------------------------------------------------------
# Final result
# ---------------------------------------------------------

print()
print("ChromaDB setup completed!")
print("Total documents:", collection.count())