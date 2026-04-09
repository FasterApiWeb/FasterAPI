// HTTP server matching Python benchmark routes (health, user get, user create).
package main

import (
	"os"

	"github.com/gofiber/fiber/v2"
)

type userBody struct {
	Name  string `json:"name"`
	Email string `json:"email"`
}

func main() {
	app := fiber.Config{
		Prefork:       false,
		CaseSensitive: true,
		StrictRouting: true,
	}
	f := fiber.New(app)

	f.Get("/health", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{"status": "ok"})
	})

	f.Get("/users/:user_id", func(c *fiber.Ctx) error {
		id := c.Params("user_id")
		return c.JSON(fiber.Map{"id": id, "name": "test"})
	})

	f.Post("/users", func(c *fiber.Ctx) error {
		var body userBody
		if err := c.BodyParser(&body); err != nil {
			return c.Status(fiber.StatusBadRequest).SendString(err.Error())
		}
		return c.JSON(fiber.Map{"name": body.Name, "email": body.Email})
	})

	_ = f.Listen(":" + listenPort())
}

func listenPort() string {
	p := getenv("PORT", "3099")
	return p
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
