# --- DTF EMPIRE MASTER SETUP SCRIPT ---
$projectRoot = "dtf_empire"

Write-Host "Creating Project Directory: $projectRoot..." -ForegroundColor Cyan
New-Item -Path $projectRoot -ItemType Directory -Force | Out-Null
New-Item -Path "$projectRoot\app" -ItemType Directory -Force | Out-Null

# ---------------------------------------------------------
# 1. Create .env
# ---------------------------------------------------------
Write-Host "Writing configuration (.env)..." -ForegroundColor Green
$envContent = @"
# Database Credentials
POSTGRES_USER=dtf_admin
POSTGRES_PASSWORD=empire_secret
POSTGRES_DB=dtf_content_db
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Application Settings
OPENAI_API_KEY=sk-placeholder-key-here
"@
Set-Content -Path "$projectRoot\.env" -Value $envContent

# ---------------------------------------------------------
# 2. Create docker-compose.yml
# ---------------------------------------------------------
Write-Host "Writing docker-compose.yml..." -ForegroundColor Green
$composeContent = @"
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_USER: `$${POSTGRES_USER}
      POSTGRES_PASSWORD: `$${POSTGRES_PASSWORD}
      POSTGRES_DB: `$${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - dtf_network

  app:
    build: ./app
    restart: always
    depends_on:
      - db
    environment:
      POSTGRES_USER: `$${POSTGRES_USER}
      POSTGRES_PASSWORD: `$${POSTGRES_PASSWORD}
      POSTGRES_DB: `$${POSTGRES_DB}
      POSTGRES_HOST: `$${POSTGRES_HOST}
      POSTGRES_PORT: `$${POSTGRES_PORT}
      OPENAI_API_KEY: `$${OPENAI_API_KEY}
    networks:
      - dtf_network

volumes:
  postgres_data:

networks:
  dtf_network:
"@
# Note: Variables in docker-compose above are escaped with backticks for PowerShell
Set-Content -Path "$projectRoot\docker-compose.yml" -Value $composeContent

# ---------------------------------------------------------
# 3. Create app/requirements.txt
# ---------------------------------------------------------
Write-Host "Writing requirements.txt..." -ForegroundColor Green
$reqContent = @"
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
python-dotenv==1.0.0
requests==2.31.0
openai==1.3.0
"@
Set-Content -Path "$projectRoot\app\requirements.txt" -Value $reqContent

# ---------------------------------------------------------
# 4. Create app/Dockerfile
# ---------------------------------------------------------
Write-Host "Writing Dockerfile..." -ForegroundColor Green
$dockerContent = @"
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-u", "main.py"]
"@
Set-Content -Path "$projectRoot\app\Dockerfile" -Value $dockerContent

# ---------------------------------------------------------
# 5. Create app/models.py
# ---------------------------------------------------------
Write-Host "Writing models.py..." -ForegroundColor Green
$modelsContent = @"
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    affiliate_link = Column(String, nullable=False)
    niche = Column(String, default="General")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    posts = relationship("ContentPost", back_populates="product")

class ContentPost(Base):
    __tablename__ = 'content_posts'

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey('products.id'))
    platform = Column(String)
    generated_copy = Column(Text)
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="posts")
"@
Set-Content -Path "$projectRoot\app\models.py" -Value $modelsContent

# ---------------------------------------------------------
# 6. Create app/database.py
# ---------------------------------------------------------
Write-Host "Writing database.py..." -ForegroundColor Green
$dbContent = @"
import os
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

def get_engine():
    retries = 5
    while retries > 0:
        try:
            print(f"Connecting to database... ({retries} retries left)")
            engine = create_engine(DATABASE_URL)
            engine.connect()
            print("Database connected successfully.")
            return engine
        except Exception as e:
            print(f"Database connection failed: {e}")
            retries -= 1
            time.sleep(5)
    raise Exception("Could not connect to the database after multiple attempts.")

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
"@
Set-Content -Path "$projectRoot\app\database.py" -Value $dbContent

# ---------------------------------------------------------
# 7. Create app/main.py
# ---------------------------------------------------------
Write-Host "Writing main.py..." -ForegroundColor Green
$mainContent = @"
import time
import os
import random
from sqlalchemy.orm import Session
from database import SessionLocal, init_db
from models import Product, ContentPost

def seed_data(db: Session):
    if db.query(Product).count() == 0:
        print("Seeding database with sample product...")
        sample = Product(
            name="Ridgid TS3650 Table Saw",
            description="A heavy duty contractor saw for precise cuts.",
            affiliate_link="http://dtf.empire/link/ridgid3650",
            niche="Construction"
        )
        db.add(sample)
        db.commit()

def generate_marketing_copy(product_name, niche):
    templates = [
        f"🔥 Check out the {product_name}! Perfect for {niche} lovers. Grab yours here: ",
        f"Stop struggling with bad tools. The {product_name} is a game changer for {niche}. Link: ",
        f"Daily Deal: {product_name}. Best in class for {niche}. Shop now: "
    ]
    return random.choice(templates)

def run_automation():
    db = SessionLocal()
    products = db.query(Product).outerjoin(ContentPost).filter(ContentPost.id == None).all()

    if not products:
        print("No new products to process. Sleeping...")
    
    for product in products:
        print(f"Processing product: {product.name}...")
        
        copy_text = generate_marketing_copy(product.name, product.niche)
        full_content = f"{copy_text} {product.affiliate_link}"
        
        new_post = ContentPost(
            product_id=product.id,
            platform="Twitter",
            generated_copy=full_content,
            is_published=False
        )
        db.add(new_post)
        db.commit()
        print(f"✅ Generated Post: {full_content}")

    db.close()

if __name__ == "__main__":
    print("Starting DTF Empire Content Engine...")
    init_db()
    
    session = SessionLocal()
    seed_data(session)
    session.close()

    while True:
        run_automation()
        time.sleep(60)
"@
Set-Content -Path "$projectRoot\app\main.py" -Value $mainContent

# ---------------------------------------------------------
# 8. LAUNCH DOCKER
# ---------------------------------------------------------
Write-Host "Files created successfully." -ForegroundColor Cyan
Write-Host "Launching Docker Containers..." -ForegroundColor Yellow

Set-Location $projectRoot
docker-compose up --build
