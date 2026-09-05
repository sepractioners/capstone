"""PartyRole enum."""
from __future__ import annotations

from enum import Enum


class PartyRole(str, Enum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    EMPLOYEE = "employee"
    EMPLOYER = "employer"
    LICENSOR = "licensor"
    LICENSEE = "licensee"
    GUARANTOR = "guarantor"
    AFFILIATE = "affiliate"
    DISTRIBUTOR = "distributor"
    FRANCHISOR = "franchisor"
    FRANCHISEE = "franchisee"
    VENDOR = "vendor"
    PARTNER = "partner"
    CONTRACTOR = "contractor"
    LESSOR = "lessor"
    LESSEE = "lessee"
    BORROWER = "borrower"
    LENDER = "lender"
    OTHER = "other"
