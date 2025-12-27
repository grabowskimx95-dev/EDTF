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
    
    # Relationship to posts
    posts = relationship("ContentPost", back_populates="product")

class ContentPost(Base):
    __tablename__ = 'content_posts'

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey('products.id'))
    platform = Column(String)  # e.g., 'Twitter', 'Blog', 'Instagram'
    generated_copy = Column(Text)
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="posts")
