
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base, relationship
import datetime as dt

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String)
    stripe_account_id = Column(String, unique=True)
    is_verified = Column(Boolean, default=False)
    free_trades_remaining = Column(Integer, default=0)
    created = Column(DateTime, default=dt.datetime.utcnow)

    reviews_given = relationship("Review", foreign_keys="[Review.reviewer_id]", back_populates="reviewer")
    reviews_received = relationship("Review", foreign_keys="[Review.reviewee_id]", back_populates="reviewee")
    referrals_made = relationship("Referral", foreign_keys="[Referral.referrer_id]", back_populates="referrer")
    referral_received = relationship("Referral", foreign_keys="[Referral.referred_user_id]", uselist=False, back_populates="referred_user")

class Deal(Base):
    __tablename__ = "deals"
    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    counterparty_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    currency = Column(String, default="usd")
    total_amount = Column(Float, nullable=False)
    status = Column(String, default="pending")
    deal_type = Column(String, default="milestone")
    trade_status = Column(String)
    payment_intent_id = Column(String)  # ADDED
    admin_notes = Column(Text)
    auto_job_id = Column(String)
    created = Column(DateTime, default=dt.datetime.utcnow)

    creator = relationship("User", foreign_keys=[creator_id])
    counterparty = relationship("User", foreign_keys=[counterparty_id])
    reviews = relationship("Review", back_populates="deal")
    disputes = relationship("Dispute", back_populates="deal")

class Milestone(Base):
    __tablename__ = "milestones"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("deals.id"), nullable=False)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    payment_intent_id = Column(String)
    transfer_id = Column(String)
    is_released = Column(Boolean, default=False)
    created = Column(DateTime, default=dt.datetime.utcnow)
    deal = relationship("Deal")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("deals.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewee_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text)
    created = Column(DateTime, default=dt.datetime.utcnow)

    deal = relationship("Deal", back_populates="reviews")
    reviewer = relationship("User", foreign_keys=[reviewer_id], back_populates="reviews_given")
    reviewee = relationship("User", foreign_keys=[reviewee_id], back_populates="reviews_received")

class Referral(Base):
    __tablename__ = "referrals"
    id = Column(Integer, primary_key=True)
    referrer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    referred_user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    reward_claimed = Column(Boolean, default=False)
    created = Column(DateTime, default=dt.datetime.utcnow)

    referrer = relationship("User", foreign_keys=[referrer_id], back_populates="referrals_made")
    referred_user = relationship("User", foreign_keys=[referred_user_id], back_populates="referral_received")

class Dispute(Base):
    __tablename__ = "disputes"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("deals.id"), nullable=False)
    raised_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False)
    proof_file_id = Column(String)
    created = Column(DateTime, default=dt.datetime.utcnow)

    deal = relationship("Deal", back_populates="disputes")
    raised_by = relationship("User")
