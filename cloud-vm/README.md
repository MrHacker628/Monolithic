# Task 6 — Hosting ShopEasy on Google Cloud VMs

| Task | What runs where | Folder |
|---|---|---|
| **6.1** | **app-vm**: ShopEasy app · **db-vm**: MySQL. They talk over **internal IP**. | [`6.1-app-and-db-vms/`](6.1-app-and-db-vms) |
| **6.2** | 3 microservices, each on **its own VM with its own MySQL database**, plus a gateway VM. **Only the gateway has an external IP.** Product data is **synced** between the databases. | [`6.2-microservices-vms/`](6.2-microservices-vms) |

All commands below are run in **Google Cloud Shell** (the `>_` icon at the top right of the Cloud Console),
so you don't need to install anything on your laptop.

---

## 0. One-time setup (both tasks)

```bash
gcloud config set project <YOUR_PROJECT_ID>
gcloud config set compute/zone asia-south1-a
gcloud config set compute/region asia-south1
gcloud services enable compute.googleapis.com iap.googleapis.com
```

**Cloud NAT.** VMs without an external IP can't reach the internet to install packages.
Cloud NAT gives them outbound-only internet access (nobody can connect *in* through it):

```bash
gcloud compute routers create nat-router --network=default --region=asia-south1
gcloud compute routers nats create nat-config --router=nat-router --region=asia-south1 \
  --auto-allocate-nat-external-ips --nat-all-subnet-ip-ranges
```

**Firewall rules:**

```bash
# VMs on the internal network may talk to each other (usually already exists as 'default-allow-internal')
gcloud compute firewall-rules create allow-internal --network=default \
  --allow=tcp,udp,icmp --source-ranges=10.128.0.0/9
# SSH into VMs that have no external IP (through Google's IAP tunnel)
gcloud compute firewall-rules create allow-iap-ssh --network=default \
  --allow=tcp:22 --source-ranges=35.235.240.0/20
# The website (port 80) - ONLY for VMs tagged 'web'
gcloud compute firewall-rules create allow-web --network=default \
  --allow=tcp:80 --target-tags=web --source-ranges=0.0.0.0/0
```
If a rule says *already exists*, that's fine.

**SSH into a VM:** in the Console go to **Compute Engine → VM instances** and click **SSH** next to the VM,
or in Cloud Shell: `gcloud compute ssh <vm-name> --tunnel-through-iap`

---

## Task 6.1 — App on VM1, database on VM2

```
   Internet ──► app-vm (external IP, port 80)  ──── internal IP ────►  db-vm (NO external IP)
                ShopEasy app                     10.x.x.x:3306         MySQL 'shopeasy' database
```

### Step 1: Create the two VMs
```bash
gcloud compute instances create db-vm --machine-type=e2-small \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud --no-address

gcloud compute instances create app-vm --machine-type=e2-small \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud --tags=web

gcloud compute instances list
```
Note **db-vm's INTERNAL_IP** (e.g. `10.160.0.2`). db-vm has no EXTERNAL_IP, so the database
can only be reached from inside the network.

### Step 2: Set up the database VM
SSH into **db-vm**, then:
```bash
git clone https://github.com/MrHacker628/Monolithic.git
cd Monolithic/cloud-vm/6.1-app-and-db-vms
sudo bash setup-db-vm.sh MyShopPass123
```
Use any password with only letters and numbers. The script installs MySQL, allows connections only from
internal IPs (`10.%`), and prints this VM's internal IP.

### Step 3: Set up the application VM
SSH into **app-vm**, then (use db-vm's internal IP and the same password):
```bash
git clone https://github.com/MrHacker628/Monolithic.git
cd Monolithic/cloud-vm/6.1-app-and-db-vms
sudo bash setup-app-vm.sh 10.160.0.2 MyShopPass123
```
The script first checks it can reach MySQL on the internal IP, then starts the app on port 80.

### Step 4: Test it
Open `http://<app-vm EXTERNAL IP>` and place an order. Then open **`http://<app-vm EXTERNAL IP>/dbinfo`**:
it shows the app connected to MySQL at db-vm's **internal IP**, with live row counts.

### Proof for your submission (6.1)
1. `gcloud compute instances list`: db-vm has **no external IP**.
2. The `/dbinfo` page showing the DB host as a `10.x.x.x` internal IP.
3. On **db-vm**, show the data and the live connection coming from app-vm's internal IP:
   ```bash
   sudo mysql -e "SELECT id, customer_name, total, status FROM shopeasy.orders;"
   sudo ss -tn state established '( sport = :3306 )'
   ```

---

## Task 6.2 — Microservices, each on its own VM with its own database

```
                        Internet
                           │  (port 80, external IP)
                    ┌──────▼──────┐
                    │ gateway-vm  │  frontend / API gateway, NO database
                    └──┬───┬───┬──┘
          internal IPs │   │   │
       ┌───────────────┘   │   └───────────────┐
┌──────▼───────┐   ┌───────▼──────┐   ┌────────▼──────┐
│  product-vm  │   │   cart-vm    │   │   order-vm    │   ← NO external IPs
│ product-svc  │──►│  cart-svc    │◄──│ order-svc     │
│ MySQL:       │   │ MySQL:       │   │ (orders +     │
│  productdb   │──►│  cartdb      │   │  payments)    │
│  (master)    │   │  (+replica)  │   │ MySQL:        │
│              │──────────────────────►  orderdb      │
└──────────────┘   └──────────────┘   │  (+replica)   │
     push sync ──►                    └───────────────┘
```

| VM | Runs | Port | Own database | External IP |
|---|---|---|---|---|
| gateway-vm | Frontend / API gateway | 80 | none | **Yes (only this one)** |
| product-vm | product-service | 5001 | `productdb` (master product data) | No |
| cart-vm | cart-service | 5002 | `cartdb` (carts + product replica) | No |
| order-vm | order-service (orders + payments) | 5003 | `orderdb` (orders, payments + product replica) | No |

### How the databases sync
- `productdb` holds the **master** product data (name, price, stock).
- `cartdb` and `orderdb` each keep a **replica** of it, so cart prices and stock checks work from their own database.
- **Push:** when a product changes (an Admin price/stock edit, or stock reduced after an order), the product
  service immediately sends the change to the cart and order services, which update their databases.
- **Pull:** every 30 seconds the cart and order services also fetch the full product list and repair any
  difference, e.g. if they were down when a push was sent.
- The **DB Sync** page compares a checksum of each database's product data and shows **IN SYNC** when all match.

### Step 1: Create the four VMs
```bash
for vm in product-vm cart-vm order-vm; do
  gcloud compute instances create $vm --machine-type=e2-small \
    --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud --no-address
done

gcloud compute instances create gateway-vm --machine-type=e2-small \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud --tags=web

gcloud compute instances list
```
Write down the **INTERNAL_IP** of product-vm, cart-vm and order-vm. Only gateway-vm has an EXTERNAL_IP.

### Step 2: Set up each VM
On **every** VM, first SSH in and run:
```bash
git clone https://github.com/MrHacker628/Monolithic.git
cd Monolithic/cloud-vm/6.2-microservices-vms
```
Then run the line for that VM, replacing the example IPs with your real internal IPs:

| SSH into | Run |
|---|---|
| product-vm | `sudo bash setup-vm.sh product <CART_IP> <ORDER_IP>` |
| cart-vm | `sudo bash setup-vm.sh cart <PRODUCT_IP>` |
| order-vm | `sudo bash setup-vm.sh order <PRODUCT_IP> <CART_IP>` |
| gateway-vm | `sudo bash setup-vm.sh gateway <PRODUCT_IP> <CART_IP> <ORDER_IP>` |

Each service VM installs its own MySQL (listening on 127.0.0.1 only, so only that VM's service can use it),
creates its database, and starts the service. The order doesn't matter much: the cart and order
services keep retrying until the product service is up.

### Step 3: Test it
Open `http://<gateway-vm EXTERNAL IP>`:
1. **Services** page: all 3 services UP, with their internal `10.x.x.x` addresses, VM hostnames and databases.
2. **DB Sync** page: *All databases are IN SYNC*, with the same checksum in productdb, cartdb and orderdb.
3. **Admin** page: change a product's price or stock and click **Save**, then reopen **DB Sync**. The new
   value already appears in all three databases.
4. Buy something, then check **DB Sync** again: the stock dropped in all three databases.

### Proof for your submission (6.2)
1. `gcloud compute instances list`: only **gateway-vm** has an external IP.
2. Screenshots of the **Services**, **DB Sync** (before and after an Admin edit), **Admin** and shop pages.
3. The services are NOT reachable from outside. From your laptop, `http://<any internal IP>:5001` doesn't
   load, and the service VMs have no external IP to try.
4. The services ARE reachable internally. On gateway-vm:
   ```bash
   curl http://<PRODUCT_IP>:5001/health
   curl http://<CART_IP>:5002/sync/status | head -c 300
   ```
5. Each VM has its own database. For example, on cart-vm:
   ```bash
   sudo mysql -e "SELECT id, name, price, stock FROM cartdb.product_replica;"
   ```

---

## Useful commands on any VM

| What | Command |
|---|---|
| Service status | `sudo systemctl status shopeasy-<role>` (6.1: `shopeasy`) |
| Service logs | `sudo journalctl -u shopeasy-<role> -n 50` |
| Restart after `git pull` | `sudo systemctl restart shopeasy-<role>` |

`<role>` is `product`, `cart`, `order` or `gateway`.

## Test on your laptop first (optional)
`cd 6.2-microservices-vms` then `pip install flask requests` then `python run_local.py`, and open http://localhost:5000.
This runs everything on one machine with SQLite instead of MySQL, so you can see the pages before deploying.

## ⚠️ Avoid charges when you are done
After your screenshots and submission, delete everything:
```bash
gcloud compute instances delete db-vm app-vm product-vm cart-vm order-vm gateway-vm --quiet
gcloud compute routers delete nat-router --region=asia-south1 --quiet
```
