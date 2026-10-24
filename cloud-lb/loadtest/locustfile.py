"""
Locust load test for ShopEasy behind the HTTP Load Balancer.
Each simulated user browses products, searches, prices a cart and places orders,
so all 3 microservices get traffic. Order placement (payment signing) and cart
pricing are CPU-heavy, which pushes the instance group above 60% CPU.
"""
import random

from locust import HttpUser, between, task

PRODUCT_IDS = list(range(1, 11))


def random_cart():
    return [{"product_id": pid, "quantity": random.randint(1, 3)}
            for pid in random.sample(PRODUCT_IDS, random.randint(1, 4))]


class Shopper(HttpUser):
    wait_time = between(0.5, 2)

    @task(3)
    def browse_products(self):
        self.client.get("/products", name="GET /products")

    @task(1)
    def search(self):
        self.client.get("/products?q=" + random.choice(["watch", "shoe", "lamp", "book", "bag"]),
                        name="GET /products?q=")

    @task(2)
    def price_cart(self):
        self.client.post("/cart/quote", json={"items": random_cart()}, name="POST /cart/quote")

    @task(2)
    def place_order(self):
        self.client.post("/orders", name="POST /orders",
                         json={"name": "Load Test", "card_number": "4242424242424242", "items": random_cart()})
