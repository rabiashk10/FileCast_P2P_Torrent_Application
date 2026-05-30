import os
import sys
import json
from hashlib import sha1



# Divides a file into pieces

# We give the req piece size
# Reads bits according to piece size, hashes them
# Makes files of each piece and writes the data
# The hashed data is stored in the metadata.json

# Metadata.json is the description of the torrent
# When we need to download this we will first get the metdata
# So that we get the hash pieces and torrent_id


def make_pieces(file_path, piece_size= 262144):
    base_name = os.path.basename(file_path)
    size = os.path.getsize(file_path)
    torent_id_hasher = sha1()
    pieces = []

    out_dir = f"torrents/torrent_{base_name}_{size}"
    pieces_dir = os.path.join(out_dir, "pieces")

    os.makedirs(pieces_dir, exist_ok=True)

    with open(file_path, "rb") as f:
        i = 0

        while True:
            data = f.read(piece_size)
            if not data:
                break

            # Hashing

            h = sha1(data).hexdigest()
            pieces.append(h)
            torent_id_hasher.update(bytes.fromhex(h))
            piece_name = os.path.join(pieces_dir, f"piece_{i:06d}.bin")


            # Creating pieces

            with open(piece_name, "wb") as pf:
                pf.write(data)
            i += 1


    torent_id = torent_id_hasher.hexdigest()


    # Makin metadata

    metadata = {
        "name": base_name,
        "length": size,
        "piece_length": piece_size,
        "pieces": pieces,
        "torrent_id": torent_id
    }

    meta_path = os.path.join(out_dir, "metadata.json")

    with open(meta_path, "w") as m:
        json.dump(metadata, m, indent=2)
    
    print(f"Created torrent dir: {out_dir}")
    print(f"No of pieces: {len(pieces)}")
    print(f"metadata.json at: {meta_path}")

    return out_dir


# sys.argv takes the arguments we provide at command line and use them in program
# Here file_path and piece_size are used in make_pieces()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python storage.py /path/to/file [piece_size_bytes]")
        sys.exit(1)
    file_path = sys.argv[1]
    piece_size = int(sys.argv[2]) if len(sys.argv) >= 3 else 262144
    make_pieces(file_path, piece_size)

