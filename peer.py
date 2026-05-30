import asyncio, os, json, argparse, struct
from hashlib import sha1
from aiobtdht import DHT


# Each packet we sending has certain messages like:

# LIST      : L --- Requests the list of available files the peer is seeding
# META      : M --- Sends the metadata.json of the selected file
# HANDSHAKE : H --- Initial msg sent to ensure the peer replies back and exchanges the torrent_id
# BITFIELD  : B --- Returns the bitfield which is an array of booleans telling which piece of file is present or not
# REQUEST   : R --- Asks the peer to send a required piece of file
# PIECE     : P --- Sends the required piece

MSG_LEN = 4


# packs msg by including the type of msg it is (H, B, R, P) and the payload which is the data of the msg
def pack_msg(msg_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(msg_type + payload)) + msg_type + payload



# Helper func to read the msg
# reads the msg
# separates the type and payload and returns
async def read_msg(reader):
    raw_len = await reader.readexactly(MSG_LEN)

    (l,) = struct.unpack(">I", raw_len)

    data = await reader.readexactly(l)

    typ = data[:1]
    payload = data[1:]

    return typ, payload


# ==================== Server shii ======================= #

async def handle_peer(reader, writer, dht, port):
    peer_address = writer.get_extra_info('peername') # getting the address (IP:PORT) of the peer

    try:

        # List

        typ, payload = await read_msg(reader= reader)

        # Loops through names of all folders in torrents directory
        # and adds their names and torrent_id in a list
        # This list is sent back to client

        if typ == b'L':

            available_shii = []

            for shii in os.listdir("torrents"):
                meta_path = os.path.join("torrents", shii, "metadata.json")

                if os.path.exists(meta_path):
                    with open(meta_path, 'r') as rf:
                        shii_metadata = json.load(rf)
                    available_shii.append({"name": shii_metadata["name"], "torrent_id": shii_metadata["torrent_id"]})
            payload = json.dumps(available_shii).encode()

            writer.write(pack_msg(b'L', payload))
            await writer.drain()

        # Meta

        # Gets the required torrent_id from the client
        # Loops through all the folders in torrent dir
        # If the torrent_id is matched in metadata of any torrent
        # Sends that metadata back to client so they can download the file

        typ, payload = await read_msg(reader= reader)
        metadata = {}
        if typ == b'M':

            torrent_id = payload.decode()

            for shii in os.listdir("torrents"):
                meta_path = os.path.join("torrents", shii, "metadata.json")

                if os.path.exists(meta_path):

                    with open(meta_path, 'r') as rf:
                        shii_metadata = json.load(rf)
                    
                    if shii_metadata["torrent_id"] == torrent_id:
                        metadata = shii_metadata
                        writer.write(pack_msg(b'M', json.dumps(shii_metadata).encode()))
                        await writer.drain()

                        # Announcing about the client of this torrent to other peers using DHT
                        await dht.announce(bytes.fromhex(torrent_id), port)
                        print(f"Announced {torrent_id} to DHT")
                        break




        # Handshake

        typ, payload = await read_msg(reader= reader)

        if typ != b'H':
            return
        
        client_tId = payload.decode()

        # Checking if torrent_id matches
        if client_tId != metadata["torrent_id"]:
            return
        
        # Sending handshake back if torrent_id matches

        writer.write(pack_msg(b'H', metadata["torrent_id"].encode()))
        await writer.drain()

        # Getting Bitfield
        n_pieces = len(metadata["pieces"])
        bitfield = [False] * n_pieces
        torrent_dir = os.path.join("torrents", f"torrent_{metadata['name']}_{metadata['length']}")
        pieces_dir = os.path.join(torrent_dir, "pieces")
        for fname in os.listdir(pieces_dir):
            if fname.startswith("piece_"):
                idx = int(fname[6:12])
                bitfield[idx] = True


        bitfield_bytes = bytearray((n_pieces + 7) // 8)

        for i in range(n_pieces):
            if bitfield[i]:         # checking if that particular (i-th) piece is available
                byte_idx = i // 8   # tells the index of byte like every byte is 8 bits thats why divide by 8
                bit_idx = i % 8     # tells the index of bit becuase after every 8 bits new byte starts

                bitfield_bytes[byte_idx] |= (1 << bit_idx)  # ok i dont know whatever shii is happening here tell me too plax

        writer.write(pack_msg(b'B', bytes(bitfield_bytes)))       
        await writer.drain()



        # Serving pieces
        
        while True:

            typ, payload = await read_msg(reader= reader)

            # Request

            if typ == b'R':
                (piece_idx,) = struct.unpack(">I", payload[:4])

                if not bitfield[piece_idx]:
                    return
                
                # getting path of piece and opening it, reading it and sending the read data

                piece_path = os.path.join(pieces_dir, f"piece_{piece_idx:06d}.bin")

                with open(piece_path, "rb") as pf:
                    piece_data = pf.read()
                
                # Piece

                writer.write(pack_msg(b'P', struct.pack(">I", piece_idx) + piece_data))
                await writer.drain()


    except asyncio.IncompleteReadError:
        pass
    finally:
        writer.close()
        await writer.wait_closed()



async def start_server_shii(host, port, dht):
    server = await asyncio.start_server(
        lambda r, w: handle_peer(r, w, dht, port),
        host= host,
        port= port
    )

    print(f"Serving on {host}:{port}")

    async with server:
        await server.serve_forever()





# ================== Client shii ========================= #

async def download_from_peer(peer_host, peer_port, dht, torrent_id_to_download=None):

    if not torrent_id_to_download:
        # If no torrent id is given then we ask for List of torrents
        try:
            reader, writer = await asyncio.open_connection(peer_host, peer_port)

            # List

            # Sends L message to peer
            # (yeah ik L message funny)
            # (more like L Chu message)

            writer.write(pack_msg(b'L', b''))
            await writer.drain()


            try:
                typ, payload = await read_msg(reader)

            except asyncio.IncompleteReadError:
                print(f"Connection closed by {peer_host}:{peer_port}")
                return

            if typ != b'L':
                print(f"No files available from {peer_host}:{peer_port}")
                return
            
            available_shii = json.loads(payload.decode())
            
            print("Available files from peer:")
            print("----------------")

            for i , shii in enumerate(available_shii):
                print(f"{i}. {shii['name']} ({shii['torrent_id']})")


            writer.close()
            await writer.wait_closed()
            return
        except ConnectionRefusedError:
            print(f"Connection refused by {peer_host}:{peer_port}")
            return
        
    
    # If torrent id is given we use the DHT to find peers having that torrent
    shii_info = bytes.fromhex(torrent_id_to_download)
    shii_from_diht = await dht[shii_info]
    print(f"No of peers found: {len(shii_from_diht)}")
    
    for peer_host, peer_port in shii_from_diht:
            await download_torrent(peer_host, peer_port, torrent_id_to_download)


async def download_torrent(peer_host, peer_port, torrent_id):

    # Establishing a connection with the peer
    reader, writer = await asyncio.open_connection(peer_host, peer_port)

    metadata = None
    pieces_dir = None
    bitfield = []    

    try:
        # Meta

        # Request metadata of the selected file from peer

        writer.write(pack_msg(b'M', torrent_id.encode()))
        await writer.drain()

        typ, payload = await read_msg(reader= reader)

        if typ != b'M':
            print(f"No metadata received from {peer_host}:{peer_port}...")
            return
        
        metadata = json.loads(payload.decode())

        # Saving metadata

        torrent_dir = os.path.join("downloads", metadata["name"])

        pieces_dir = os.path.join(torrent_dir, "pieces")

        os.makedirs(pieces_dir, exist_ok= True)

        with open(os.path.join(torrent_dir, "metadata.json"), 'w') as wf:
            json.dump(metadata, wf, indent= 2)


        # Initializing bitfield

        n_pieces = len(metadata["pieces"])
        bitfield = [False] * n_pieces

        for fname in os.listdir(pieces_dir):
            if fname.startswith("piece_"):
                idx = int(fname[6:12])
                bitfield[idx] = True


        # Handshake

        writer.write(pack_msg(b'H', metadata["torrent_id"].encode()))
        await writer.drain()

        typ, payload = await read_msg(reader= reader)

        if typ != b'H':
            print("Handshake failed...")
            return
        
        # Bitfield

        typ, payload = await read_msg(reader= reader)

        if typ != b'B':
            print("Did not receive bitfield...")
            return
        
        peer_bitfield = [False] * n_pieces   # initialize bitfield with all false at start

        for i in range(n_pieces):
            byte_idx = i // 8
            bit_idx = i % 8

            if byte_idx < len(payload):
                peer_bitfield[i] = bool(payload[byte_idx] & (1 << bit_idx)) # ok i again dont know whatever shii is going on here

        # Request missing pieces

        for i in range(n_pieces):

            if bitfield[i]: # Piece already present so we skip it
                continue

            if not peer_bitfield[i]: # Peer does not have the piece
                continue

            # Request

            writer.write(pack_msg(b'R', struct.pack(">I", i)))
            await writer.drain()

            # Piece

            typ, payload = await read_msg(reader= reader)

            if typ != b'P':
                continue

            (recv_idx,) = struct.unpack(">I", payload[:4])

            if recv_idx != i: # Did not receive right piece
                continue

            piece_data = payload[4:]

            # Saving piece

            piece_path = os.path.join(pieces_dir, f"piece_{i:06d}.bin")

            with open(piece_path, "wb") as f:
                f.write(piece_data)
            
            # Verifying hash of file to check

            expected = metadata["pieces"][i]

            got = sha1(piece_data).hexdigest()

            if got != expected:
                print(f"SHA missmatch piece {i}")
            else:
                bitfield[i] = True
                print(f"Downloaded piece {i + 1}/{n_pieces} from {peer_host}:{peer_port}")



        # Check if we now have all pieces

        if all(bitfield):

            # Assemble the pieces

            out_file = os.path.join(os.path.dirname(pieces_dir), "downloaded_" + metadata["name"])
            with open(out_file, "wb") as out:
                for i in range(len(metadata["pieces"])):
                    piece_path = os.path.join(pieces_dir, f"piece_{i:06d}.bin")
                    with open(piece_path, "rb") as pf:
                        out.write(pf.read())
            print(f"All pieces downloaded. File assembled at: {out_file}")
            print("**************************************************************")
            print("**************************************************************")


    finally:
        writer.close()
        await writer.wait_closed()
        



# =========================== Main ================================== #

async def main(port, peers, torrent_id):

    host = "0.0.0.0"


    # Initializing the DHT

    dht = DHT()

    await dht.run(port= port)

    # Here we add some classic DHT servers 
    # These serve as an entry point to direct the dht towards the peers
    # These are pulic peers that are always online and direct the traffic towards others

    bootstrap_shii = [
        ("router.utorrent.com", 6881),
        ("router.bittorrent.com", 6881),
        ("dht.transmissionbt.com", 6881),
    ]

    await dht.bootstrap(bootstrap_shii)
    print("DHT Bootstrapped")




    # Start Server

    server_task = asyncio.create_task(
        start_server_shii(
            host= host,
            port= port,
            dht= dht
        )
        )


    # Add all client tasks

    client_tasks = []

    if torrent_id:

        # If torrent_id is provided, we use DHT to find peers
        client_tasks.append(
            download_from_peer(None, None, dht, torrent_id)
        )
    else:

        # If no torrent ID, getting the list of available files from specified peers
        # and adding all peers from whom to download

        for peer in peers:
            phost, pport = peer.split(":")
            client_tasks.append(
                download_from_peer(
                    peer_host= phost,
                    peer_port= int(pport),
                    dht= dht
                )
                )
        

    # Run all shii

    await asyncio.gather(server_task, *client_tasks)



if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default= 6881, type= int)
    parser.add_argument("--peers", default= "", help= "Comma separated host:port")
    parser.add_argument("--download", default="", help="Torrent ID of the file to download")

    args = parser.parse_args()

    peers = [x for x in args.peers.split(",") if x]

    asyncio.run(main(args.port, peers, args.download))


