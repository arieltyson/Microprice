variable "project" {
  type    = string
  default = "microprice"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "instance_type" {
  type    = string
  default = "t3.medium"
}

variable "allowed_cidr" {
  description = "CIDR allowed to reach the dashboard, for example your own IP as x.x.x.x/32"
  type        = string
}
