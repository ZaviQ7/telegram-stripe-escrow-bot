import stripe
from typing import Dict, Optional

class StripeHelper:
    def __init__(self, secret_key: str):
        """Initialise the Stripe helper with the provided secret key."""
        stripe.api_key = secret_key
        self.stripe = stripe

    def create_express_account(self) -> str:
        """Creates a new Stripe Express account and returns its ID."""
        acct = self.stripe.Account.create(type="express")
        return acct["id"]

    def onboarding_url(self, account_id: str, refresh_url: str, return_url: str) -> str:
        """Creates an account link for onboarding a user."""
        link = self.stripe.AccountLink.create(
            account=account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding",
        )
        return link["url"]

    def create_checkout_session(
        self,
        deal_id: int,
        deal_title: str,
        amount: float,
        currency: str,
        success_url: str,
        cancel_url: str,
        application_fee_cents: int = 0,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Create a Stripe Checkout session for either a one-time trade or a
        milestone payment.
        """
        # Build metadata - always include the deal ID
        if metadata is None:
            metadata_data = {"deal_id": str(deal_id)}
        else:
            metadata_data = metadata.copy()
            metadata_data.setdefault("deal_id", str(deal_id))

        transfer_group_id = metadata_data.get("deal_id", str(deal_id))
        payment_intent_data = {
            "metadata": metadata_data,
            "transfer_group": f"deal-{transfer_group_id}",
        }
        if application_fee_cents and application_fee_cents > 0:
            payment_intent_data["application_fee_amount"] = application_fee_cents

        session = self.stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": currency,
                        "product_data": {
                            "name": f"Escrow for '{deal_title}'",
                            "description": f"Deal ID: {deal_id}",
                        },
                        "unit_amount": int(amount * 100),
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            payment_intent_data=payment_intent_data,
        )
        return session.url

    def transfer(self, amount: float, currency: str, destination: str, transfer_group: str) -> str:
        """Transfer funds to a connected account."""
        tx = self.stripe.Transfer.create(
            amount=int(amount * 100),
            currency=currency,
            destination=destination,
            transfer_group=transfer_group,
        )
        return tx["id"]

    def refund_payment(self, payment_intent_id: str, amount_cents: int = None) -> str:
        """Refund all or part of a payment intent."""
        params = {"payment_intent": payment_intent_id}
        if amount_cents:
            params["amount"] = amount_cents
        refund = self.stripe.Refund.create(**params)
        return refund.id