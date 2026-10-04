"""Beneficiaries: saved suppliers and others, their payout details, verification and paying them."""

from decimal import Decimal

from accounting.models import BusinessEntry
from audit.models import AuditEvent

from .models import Membership, Payment
from .tests import BusinessTestCase, make_user, personal_wallet


class BeneficiaryTests(BusinessTestCase):
    def setUp(self):
        super().setUp()
        self.fiona = self.add_member("fiona@acme.test", "Fiona Finance", Membership.Role.FINANCE)
        self.org.approval_threshold = Decimal("1000.00")
        self.org.save()

    def add(self, user, **data):
        body = {"name": "Oscar Stationery", "kind": "SUPPLIER", "method": "FLUXPAY",
                "account_number": personal_wallet(self.outsider).account_number, **data}  # fmt: skip
        return self.as_user(user).post(self.url("beneficiaries/"), body, format="json")

    def verify(self, user, beneficiary_id):
        return self.as_user(user).post(self.url(f"beneficiaries/{beneficiary_id}/verify/"))

    def change(self, user, beneficiary_id, **data):
        return self.as_user(user).patch(self.url(f"beneficiaries/{beneficiary_id}/"), data, format="json")

    def pay(self, user, beneficiary_id, amount="200.00", key="pay-beneficiary-1", **extra):
        body = {"beneficiary_id": beneficiary_id, "amount": amount, "idempotency_key": key, **extra}
        return self.as_user(user).post(self.url("payments/"), body, format="json")

    def test_entered_by_finance_verified_by_an_owner_then_paid(self):
        res = self.add(self.fiona)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertFalse(res.data["is_verified"])
        beneficiary = res.data["id"]
        self.assertEqual(self.pay(self.fiona, beneficiary).data["error"]["code"], "beneficiary_unverified")
        self.assertEqual(self.verify(self.fiona, beneficiary).status_code, 403)  # finance can't verify

        res = self.verify(self.owner, beneficiary)
        self.assertEqual((res.data["is_verified"], res.data["verified_by"]), (True, "Olivia Owner"))
        res = self.pay(self.fiona, beneficiary, note="Invoice 77")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(
            (res.data["status"], res.data["type"], res.data["recipient_name"], str(res.data["beneficiary_id"])),
            ("COMPLETED", "SUPPLIER", "Oscar Stationery", beneficiary),
        )
        self.assertEqual(self.balance(personal_wallet(self.outsider)), Decimal("1200.00"))
        entry = BusinessEntry.objects.get(reference=res.data["reference"])
        self.assertEqual(entry.category.name, "Purchases and suppliers")
        payment = Payment.objects.get(id=res.data["id"])
        self.assertEqual(payment.beneficiary_details["account_number"], personal_wallet(self.outsider).account_number)
        listed = self.as_user(self.owner).get(self.url("payments/"), {"beneficiary": beneficiary}).data["results"]
        self.assertEqual([p["id"] for p in listed], [res.data["id"]])

    def test_the_kind_sets_how_a_payment_is_filed(self):
        beneficiary = self.add(self.owner, name="Office Landlord", kind="LANDLORD").data["id"]
        self.verify(self.owner, beneficiary)
        res = self.pay(self.owner, beneficiary)
        self.assertEqual((res.data["type"], res.data["type_label"]), ("EXPENSE", "Business expense"))
        self.assertEqual(BusinessEntry.objects.get(reference=res.data["reference"]).category.name,
                         "Other business expenses")  # fmt: skip
        salary = self.pay(self.owner, beneficiary, key="landlord-salary", type="SALARY")
        self.assertEqual(salary.status_code, 400)

    def test_changed_payout_details_must_be_verified_again_by_someone_else(self):
        beneficiary = self.add(self.owner).data["id"]
        self.assertEqual(self.verify(self.owner, beneficiary).status_code, 200)  # the only approver may self-verify
        adam = self.add_member("adam@acme.test", "Adam Admin", Membership.Role.ADMIN)

        self.assertTrue(self.change(adam, beneficiary, notes="Pays on the 5th").data["is_verified"])  # not payout
        new_wallet = personal_wallet(make_user("mallory@else.test", "Mallory"))
        res = self.change(adam, beneficiary, account_number=new_wallet.account_number)
        self.assertFalse(res.data["is_verified"])
        self.assertEqual(self.pay(self.owner, beneficiary).data["error"]["code"], "beneficiary_unverified")
        event = AuditEvent.objects.get(action="org.beneficiary.details_changed")
        self.assertEqual(event.metadata["after"]["account_number"], new_wallet.account_number)

        self.assertEqual(self.verify(adam, beneficiary).data["error"]["code"], "self_verification")
        self.assertEqual(self.verify(self.owner, beneficiary).status_code, 200)

    def test_payment_fails_if_details_change_while_it_waits_for_approval(self):
        beneficiary = self.add(self.owner).data["id"]
        self.verify(self.owner, beneficiary)
        adam = self.add_member("adam@acme.test", "Adam Admin", Membership.Role.ADMIN)
        self.org.approval_threshold = Decimal("0.00")
        self.org.save()
        waiting = self.pay(self.fiona, beneficiary, amount="50.00", key="waits-for-approval").data
        self.assertEqual(waiting["status"], "PENDING_APPROVAL")

        other = personal_wallet(make_user("mallory@else.test", "Mallory"))
        self.change(adam, beneficiary, account_number=other.account_number)
        self.verify(self.owner, beneficiary)
        res = self.as_user(adam).post(self.url(f"payments/{waiting['id']}/approve/"))
        self.assertEqual(res.data["status"], "FAILED")
        self.assertIn("changed after this payment was created", res.data["failure_reason"])
        self.assertEqual(self.balance(other), Decimal("1000.00"))  # only the welcome bonus

    def test_payout_details_are_checked_for_each_method(self):
        res = self.add(self.owner, method="MPESA_MOBILE", mpesa_phone="0712 345 678")
        self.assertEqual(res.data["details"], {"mpesa_phone": "+254712345678"})
        cases = [
            ({"method": "MPESA_MOBILE", "mpesa_phone": "+447700900123"}, "invalid_phone"),
            ({"method": "MPESA_PAYBILL", "paybill_number": "12", "paybill_account": "A1"}, "invalid_paybill"),
            ({"method": "MPESA_TILL", "till_number": "12ab"}, "invalid_till"),
            ({"method": "BANK", "bank_account_number": "0123456789"}, "bank_details_required"),
            ({"method": "BANK", "bank_name": "KCB", "bank_account_name": "Oscar", "bank_account_number": "12-34",
              "bank_swift_code": ""}, "invalid_bank_account"),
            ({"method": "FLUXPAY", "account_number": self.wallet.account_number}, "same_account"),
        ]  # fmt: skip
        for i, (data, code) in enumerate(cases):
            res = self.add(self.owner, name=f"Case {i}", **data)
            self.assertEqual(res.data["error"]["code"], code, data)

        beneficiary = self.add(self.owner, name="Kenya Power", kind="UTILITY", method="MPESA_PAYBILL",
                                     paybill_number="888880", paybill_account="12345678").data["id"]  # fmt: skip
        res = self.change(self.owner, beneficiary, method="MPESA_TILL", till_number="5123456")
        self.assertEqual(res.data["details"], {"till_number": "5123456"})  # the paybill details are gone

    def test_mpesa_and_bank_beneficiaries_cant_be_paid_yet(self):
        beneficiary = self.add(self.owner, method="MPESA_MOBILE", mpesa_phone="0712345678").data["id"]
        self.verify(self.owner, beneficiary)
        self.assertEqual(self.pay(self.owner, beneficiary).data["error"]["code"], "payout_method_unavailable")

    def test_viewers_see_masked_details_and_other_businesses_nothing(self):
        number = personal_wallet(self.outsider).account_number
        self.add(self.owner)
        viewer = self.add_member("vic@acme.test", "Vic Viewer", Membership.Role.VIEWER)
        listed = self.as_user(viewer).get(self.url("beneficiaries/")).data["results"]
        self.assertEqual(listed[0]["details"], {"account_number": "•••• " + number[-4:]})
        self.assertEqual(self.add(viewer, name="Sneaky").status_code, 403)
        self.assertEqual(self.as_user(self.outsider).get(self.url("beneficiaries/")).status_code, 404)

    def test_archived_and_duplicate_names(self):
        beneficiary = self.add(self.owner).data["id"]
        self.assertEqual(self.add(self.owner, name="oscar stationery").data["error"]["code"], "duplicate_beneficiary")
        self.verify(self.owner, beneficiary)
        archived = self.as_user(self.owner).delete(self.url(f"beneficiaries/{beneficiary}/"))
        self.assertFalse(archived.data["is_active"])
        self.assertEqual(self.as_user(self.owner).get(self.url("beneficiaries/")).data["results"], [])
        self.assertEqual(self.pay(self.owner, beneficiary).data["error"]["code"], "beneficiary_archived")
        self.assertEqual(self.add(self.owner).status_code, 201)  # the name is free again
