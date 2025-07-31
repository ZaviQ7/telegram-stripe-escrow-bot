
import stripe
class StripeHelper:
    def __init__(self, secret_key: str):
        stripe.api_key = secret_key
        self.stripe = stripe
    def create_checkout_session(self, deal_id: int, deal_title: str, amount: float, currency: str, success_url: str, cancel_url: str, application_fee_cents: int = 0) -> str:
        payment_intent_data = {
            "metadata": {"deal_id": str(deal_id)},
            "transfer_group": f"deal-{deal_id}",
        }
        if application_fee_cents > 0:
            payment_intent_data["application_fee_amount"] = application_fee_cents
        session = self.stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': currency,
                    'product_data': {
                        'name': f"Escrow for '{deal_title}'",
                        'description': f"Deal ID: {deal_id}"
                    },
                    'unit_amount': int(amount * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            payment_intent_data=payment_intent_data
        )
        return session.url
    def transfer(self, amount: float, currency: str, destination: str, transfer_group: str):
        tx = self.stripe.Transfer.create(
            amount=int(amount * 100),
            currency=currency,
            destination=destination,
            transfer_group=transfer_group,
        )
        return tx["id"]
    def refund_payment(self, payment_intent_id: str, amount_cents: int = None) -> str:
        params = {'payment_intent': payment_intent_id}
        if amount_cents:
            params['amount'] = amount_cents
        refund = self.stripe.Refund.create(**params)
        return refund.id
